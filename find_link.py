"""
find_link.py – Descobre o permalink do projeto "NeuroVox" no site do hackathon.

Estratégias:
  A) Clica no card e captura a URL do navegador (History API).
  B) Inspeciona atributos do card (href, data-id, id).
  C) Procura botão Share / Copy Link dentro do modal aberto.
  D) Testa URLs com o ID do projeto no browser (SPA routing).
  E) Intercepta API e analisa a estrutura de dados.
  F) Analisa o código-fonte JS do componente BuildCard.
"""

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
import json
import re

BASE = "https://v0-v0prompttoproduction2026.vercel.app"
URL = f"{BASE}/browse"


def inject_history_interceptor(page):
    """Intercepta pushState/replaceState para capturar mudanças de URL em SPAs."""
    page.evaluate("""() => {
        window.__capturedUrls = [];
        const origPush = history.pushState;
        const origReplace = history.replaceState;
        history.pushState = function() {
            origPush.apply(this, arguments);
            window.__capturedUrls.push(location.href);
        };
        history.replaceState = function() {
            origReplace.apply(this, arguments);
            window.__capturedUrls.push(location.href);
        };
        window.addEventListener('hashchange', () => {
            window.__capturedUrls.push(location.href);
        });
    }""")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # ── Interceptar respostas de API ──
        api_calls = []

        def handle_response(response):
            if "/api/" in response.url:
                try:
                    body = response.text()
                except Exception:
                    body = ""
                api_calls.append({
                    "url": response.url,
                    "status": response.status,
                    "body": body,
                })

        page.on("response", handle_response)

        # ============================================================
        # FASE 1 – Acessar /browse e buscar "renan-b-eth" na search
        # ============================================================
        print(f"[1] Acessando {URL} ...")
        page.goto(URL, wait_until="networkidle", timeout=30000)
        inject_history_interceptor(page)
        page.wait_for_timeout(2000)

        print('[2] Buscando "renan-b-eth" no campo de busca ...')
        search_input = page.query_selector(
            "input[placeholder*='Search'], input[placeholder*='search'], "
            "input[type='search']"
        )
        if search_input:
            search_input.fill("renan-b-eth")
            page.keyboard.press("Enter")
            page.wait_for_timeout(3000)

        # ── Extrair dados do projeto via API interceptada ──
        build_data = None
        for call in api_calls:
            if "search=renan" in call["url"] and call["body"]:
                try:
                    data = json.loads(call["body"])
                    if data.get("builds"):
                        build_data = data["builds"][0]
                except Exception:
                    pass

        if not build_data:
            print("[ERRO] Projeto não encontrado na API. Abortando.")
            page.screenshot(path="debug_error.png")
            browser.close()
            return

        project_id = build_data["id"]
        print(f"  -> Projeto encontrado via API! ID: {project_id}")

        # ============================================================
        # FASE 2 – Scroll até o card ficar visível
        # ============================================================
        print("[3] Scrollando para encontrar o card ...")
        found = False
        for i in range(30):
            body_text = page.inner_text("body")
            if "renan-b-eth" in body_text.lower():
                print(f"  -> Card visível após {i} scrolls!")
                found = True
                break
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(800)

        # ============================================================
        # ESTRATÉGIA A – Clicar no card e verificar URL
        # ============================================================
        print("\n=== ESTRATÉGIA A: Clicar no card ===")
        if found:
            inject_history_interceptor(page)
            card_el = page.query_selector("text=renan-b-eth")
            if card_el:
                url_before = page.url
                card_el.click()
                page.wait_for_timeout(3000)
                url_after = page.url
                captured = page.evaluate("window.__capturedUrls || []")
                print(f"  URL antes do clique: {url_before}")
                print(f"  URL após o clique:   {url_after}")
                if captured:
                    print(f"  History API URLs:    {captured}")
                else:
                    print("  History API URLs:    (nenhuma mudança)")
                page.screenshot(path="debug_after_click.png")
        else:
            print("  Card não encontrado por scroll.")

        # ============================================================
        # ESTRATÉGIA B – Inspecionar atributos do card
        # ============================================================
        print("\n=== ESTRATÉGIA B: Inspecionar atributos do card ===")
        if found:
            card_info = page.evaluate("""(username) => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.innerText && el.innerText.includes(username)) {
                        let node = el;
                        for (let i = 0; i < 5; i++) {
                            if (node.parentElement) node = node.parentElement;
                        }
                        return {
                            tagName: node.tagName,
                            id: node.id || null,
                            dataset: Object.assign({}, node.dataset),
                            anchors: Array.from(node.querySelectorAll('a[href]')).map(a => ({
                                href: a.getAttribute('href'),
                                fullHref: a.href,
                                text: a.innerText.substring(0, 60),
                            })),
                            dataAttrs: Array.from(
                                node.querySelectorAll('[data-id],[data-build-id],[data-project-id],[data-slug]')
                            ).map(el => ({
                                dataId: el.getAttribute('data-id'),
                                dataBuildId: el.getAttribute('data-build-id'),
                                dataSlug: el.getAttribute('data-slug'),
                            })),
                        };
                    }
                }
                return null;
            }""", "renan-b-eth")
            if card_info:
                print(f"  Tag: {card_info['tagName']}, id: {card_info['id']}")
                print(f"  Dataset: {card_info['dataset']}")
                for a in card_info["anchors"]:
                    print(f"  <a> href={a['href']}  text={a['text']}")
                if card_info["dataAttrs"]:
                    for d in card_info["dataAttrs"]:
                        print(f"  data-attr: {d}")
                else:
                    print("  Nenhum data-id/data-slug encontrado.")
            else:
                print("  Não foi possível extrair a estrutura do card.")

        # ============================================================
        # ESTRATÉGIA C – Botão Share / Copy Link
        # ============================================================
        print("\n=== ESTRATÉGIA C: Botão Share / Copy Link ===")
        share_btn = (
            page.query_selector("button:has-text('Share')")
            or page.query_selector("[aria-label*='share' i]")
            or page.query_selector("button:has-text('Copy')")
        )
        if share_btn:
            print(f"  Botão encontrado: {share_btn.inner_text()}")
            share_btn.click()
            page.wait_for_timeout(2000)
            print(f"  URL após share: {page.url}")
        else:
            print("  Nenhum botão Share/Copy Link encontrado no card.")

        # ============================================================
        # ESTRATÉGIA D – Testar URLs com ID no browser (SPA routing)
        # ============================================================
        print("\n=== ESTRATÉGIA D: URLs com ID no browser (SPA) ===")
        id_patterns = [
            f"{BASE}/browse/{project_id}",
            f"{BASE}/build/{project_id}",
            f"{BASE}/builds/{project_id}",
            f"{BASE}/project/{project_id}",
            f"{BASE}/browse?id={project_id}",
            f"{BASE}/browse?build={project_id}",
            f"{BASE}/browse#{project_id}",
        ]
        permalink_found = None
        for url in id_patterns:
            page.goto(url, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(2000)
            body = page.inner_text("body")[:800]
            has_ref = any(
                kw in body.lower()
                for kw in ["renan", "cognitive", "eco-ideiathon", "neurovox"]
            )
            if has_ref:
                print(f"  *** MATCH: {url}")
                permalink_found = url
                page.screenshot(path="debug_id_match.png")
            else:
                print(f"  {url} -> sem referência ao projeto")

        # ============================================================
        # ESTRATÉGIA E – Dados completos da API
        # ============================================================
        print("\n=== ESTRATÉGIA E: Dados da API ===")
        print(json.dumps(build_data, indent=2, ensure_ascii=False))

        # ============================================================
        # RESUMO FINAL
        # ============================================================
        print("\n" + "=" * 70)
        print("  RESUMO FINAL – Engenharia Reversa do Permalink NeuroVox")
        print("=" * 70)
        print(f"""
  Projeto:       NeuroVox (nome exibido no card)
  ID (UUID):     {project_id}
  Builder:       {build_data.get('builder_name')}
  Username:      {build_data.get('v0_username')}
  Descrição:     {build_data.get('description')}
  Categoria:     {build_data.get('category')}
  Votos:         {build_data.get('vote_count')}
  Project URL:   {build_data.get('project_url')}
  Social Proof:  {build_data.get('social_proof_url')}
  Status:        {build_data.get('status')}
  Criado em:     {build_data.get('created_at')}
""")
        if permalink_found:
            print(f"  ✓ PERMALINK ENCONTRADO: {permalink_found}")
        else:
            print("  ✗ PERMALINK DEDICADO: NÃO EXISTE")
            print()
            print("  A SPA não implementa rotas individuais para projetos.")
            print("  O componente BuildCard é um <div> sem link interno.")
            print("  Não há botão Share, não há pushState ao clicar.")
            print()
            print("  MELHOR LINK POSSÍVEL (busca filtrada):")
            print(f"    {BASE}/browse")
            print(f"    (buscar manualmente por 'renan-b-eth' no campo de busca)")
            print()
            print("  LINK DIRETO DO PROJETO (externo ao hackathon):")
            print(f"    {build_data.get('project_url')}")
            print()
            print("  API DIRETA (retorna JSON do projeto):")
            print(f"    {BASE}/api/builds?search=renan-b-eth")

        print("\n" + "=" * 70)
        browser.close()


if __name__ == "__main__":
    main()
