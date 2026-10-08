"""
Scraper pour Trendyol (trendyol.com).

Trendyol est une SPA React — tout le contenu est chargé en JavaScript.
Stratégie : Playwright (navigateur headless Chrome) + sélecteurs CSS validés.

Sélecteurs Trendyol (juillet 2025) :
  Titre  : h1.pr-new-br  ou  [class*='product-name']
  Marque : a.product-brand-name  ou  [class*='brand-name']
  Prix   : [class*='prc-dsc']  (prix soldé) ou [class*='product-price-container']
  Images : [class*='gallery-modal'] img  ou données JSON embarquées
"""
import re
import time
import random
import json
from bs4 import BeautifulSoup

from utils import extract_jsonld_products, normalize_images, parse_price
from scrapers import playwright_manager as pm


def _handle_country_selector(page):
    """
    Trendyol redirige vers /en/select-country pour les IPs hors Turquie.
    Utilise JavaScript direct (bypass overlay cookie + React event handling).
    Structure : div.country (cliquable) + div.country-actions > button "Select"
    """
    if "select-country" not in page.url:
        return
    print("  [Trendyol] Sélecteur de pays → sélection UAE via JS")

    # 1. Accepter les cookies via JS (bypasse l'overlay OneTrust)
    page.evaluate("""
        () => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const acceptBtn = buttons.find(b =>
                b.textContent.includes('Kabul Et') ||
                b.textContent.includes('İzin Ver') ||
                b.textContent.includes('Accept') ||
                (b.id && b.id.includes('accept'))
            );
            if (acceptBtn) acceptBtn.click();
        }
    """)
    time.sleep(1)

    # 2. Sélectionner UAE dans la liste pays (div.country)
    # Ce clic déclenche une navigation directe → ne pas évaluer JS après
    try:
        page.evaluate("""
            () => {
                const divs = Array.from(document.querySelectorAll('div.country'));
                const target = divs.find(d =>
                    d.textContent.includes('United Arab Emirates') ||
                    d.textContent.includes('UAE')
                ) || divs.find(d => d.textContent.includes('Germany'))
                  || divs[0];
                if (target) target.click();
            }
        """)
    except Exception:
        pass  # Navigation déclenchée = contexte détruit = normal

    time.sleep(1)

    # 3. Cliquer "Select" seulement si toujours sur select-country
    if "select-country" in page.url:
        try:
            page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const selectBtn = btns.find(b => b.textContent.trim() === 'Select')
                                   || document.querySelector('div.country-actions button');
                    if (selectBtn) selectBtn.click();
                }
            """)
        except Exception:
            pass

    time.sleep(3)


def scrape(url: str, session) -> dict:
    result = {
        "titre": "", "marque": "", "prix": "",
        "devise": "AED", "description": "", "liens_images": [],
    }

    from playwright.sync_api import TimeoutError as PWTimeout

    # Forcer l'URL internationale /en/ pour éviter la redirect country-selector
    if "/en/" not in url:
        url = url.replace("trendyol.com/", "trendyol.com/en/", 1)

    page = pm.get_page()

    # Navigation
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PWTimeout:
        time.sleep(5)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

    # Gérer le sélecteur de pays (redirection pour IPs hors-Turquie)
    if "select-country" in page.url:
        try:
            _handle_country_selector(page)
        except Exception:
            pass
        # Attendre que l'URL quitte la page select-country (navigate via cb=)
        try:
            page.wait_for_url(lambda u: "select-country" not in u, timeout=15_000)
        except PWTimeout:
            pass
        time.sleep(2)

    # Si on n'est toujours pas sur la page produit → fallback URL turque (sans /en/)
    if "-p-" not in page.url:
        # Supprimer /en/ pour accéder à la version turque (pas de sélecteur de pays)
        tr_url = url.replace("/en/", "/")
        print(f"  [Trendyol] Fallback URL turque : {tr_url}")
        try:
            page.goto(tr_url, wait_until="domcontentloaded", timeout=60_000)
        except PWTimeout:
            pass

    # Attendre le contenu produit
    try:
        page.wait_for_selector(
            "h1.pr-new-br, [class*='product-name'], [class*='prc-dsc'], [class*='prc-org']",
            timeout=25_000,
        )
    except PWTimeout:
        pass

    # Dismisser le cookie banner sur la page produit (réapparaît à chaque navigation)
    try:
        page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const acceptBtn = buttons.find(b =>
                    b.textContent.includes('Kabul Et') ||
                    b.textContent.includes('İzin Ver') ||
                    b.textContent.includes('Accept') ||
                    (b.id && b.id.includes('accept'))
                );
                if (acceptBtn) acceptBtn.click();
            }
        """)
        time.sleep(0.5)
    except Exception:
        pass

    time.sleep(random.uniform(2, 4))
    html = page.content()
    soup = BeautifulSoup(html, "lxml")

    # 1. JSON-LD
    products = extract_jsonld_products(soup)
    if products:
        p = products[0]
        result["titre"] = p.get("name", "") or ""
        brand = p.get("brand")
        result["marque"] = (brand.get("name") if isinstance(brand, dict) else brand or "") or ""
        result["liens_images"] = [
            u for u in normalize_images(p.get("image"))
            if u and "cookielaw" not in u and "onetrust" not in u
        ]
        offers = p.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0]
        result["prix"] = parse_price(offers.get("price"))
        result["devise"] = offers.get("priceCurrency", "AED") or "AED"

    # 2. CSS fallback — titre
    if not result["titre"]:
        for sel in ["h1.pr-new-br", "[class*='product-name']", "h1"]:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(strip=True)
                # Ignorer les titres génériques de la homepage
                if text and "welcome" not in text.lower() and len(text) > 5:
                    result["titre"] = text
                    break

    # 3. CSS fallback — marque
    if not result["marque"]:
        for sel in ["a.product-brand-name", "[class*='brand-name']",
                    "[class*='product-brand']"]:
            tag = soup.select_one(sel)
            if tag:
                result["marque"] = tag.get_text(strip=True)
                break

    # 4. CSS fallback — prix (sélecteurs multi-layouts Trendyol)
    if not result["prix"]:
        for sel in [
            # Layout Samsung/téléphones (validé)
            "[class*='p-sale-price']",
            "[class*='p-price-section']",
            "[class*='p-price-wrapper']",
            "[class*='int-price']",
            # Layout iPhone / anciens produits
            "[class*='prc-dsc']",
            "[class*='prc-org']",
            # Fallbacks génériques
            "[class*='product-price-container']",
            "[class*='price-wrapper']",
            "span[class*='price']",
        ]:
            tag = soup.select_one(sel)
            if tag:
                result["prix"] = parse_price(tag.get_text(strip=True))
                if result["prix"]:
                    break

    # 5. Description
    if not result["description"]:
        for sel in ["[class*='product-description']", "[class*='detail-desc']",
                    "[class*='info-wrapper']"]:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(" ", strip=True)
                if len(text) > 20:
                    result["description"] = text[:2000]
                    break

    # Domaines/chemins à exclure (logos OneTrust, images footer Trendyol, etc.)
    EXCLUDED_DOMAINS = (
        "cookielaw.org", "onetrust", "cdn.cookielaw",
        "sfweb-browsing",   # images footer/site Trendyol (pci-dss, iso, etc.)
        "static.trendyol",  # assets statiques
    )

    def _is_product_img(url: str) -> bool:
        if not url:
            return False
        if any(d in url for d in EXCLUDED_DOMAINS):
            return False
        return True

    # 6. Images — JSON embarqué
    if not result["liens_images"]:
        m = re.search(
            r'window\.__PRODUCT_DETAIL_APP_INITIAL_STATE__\s*=\s*(\{.+?\})\s*;',
            html, re.DOTALL,
        )
        if m:
            try:
                state = json.loads(m.group(1))
                imgs = (state.get("product", {}).get("images") or
                        state.get("images") or [])
                result["liens_images"] = [
                    i if isinstance(i, str) else i.get("url", "")
                    for i in imgs if i
                ]
            except Exception:
                pass

    # Filtrer les URLs non-produit (OneTrust, etc.)
    result["liens_images"] = [u for u in result["liens_images"] if _is_product_img(u)]

    # Filtrer aussi depuis JSON-LD si présent
    if result["liens_images"] == [] and "liens_images" in result:
        pass  # déjà vide

    # 7. Images — fallback CSS
    if not result["liens_images"]:
        seen = set()
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if ("trendyol" in src or "trendcdn" in src or "dsmcdn" in src) and src not in seen:
                if _is_product_img(src) and any(ext in src for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    seen.add(src)
                    result["liens_images"].append(src)

    return result
