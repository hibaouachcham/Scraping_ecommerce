"""
Scraper pour Wildberries (wildberries.ru).

Stratégie :
  1. API interne card.wb.ru   (JSON, pas de JS requis)
  2. Playwright persistant    (UN seul navigateur pour toute la session)

Pourquoi persistant : WB détecte les nouveaux navigateurs répétés (même IP,
même fingerprint relancé en boucle). Avec un navigateur unique qui navigue
de page en page, on ressemble à un vrai utilisateur qui browse le site.

Pré-requis (une seule fois) :
    pip install playwright playwright-stealth
    python -m playwright install chromium
"""
import re
import time
import random

import requests

from utils import extract_jsonld_products, normalize_images, parse_price

# ---------------------------------------------------------------------------
# API interne Wildberries
# ---------------------------------------------------------------------------
_WB_API = (
    "https://card.wb.ru/cards/v2/detail"
    "?appType=1&curr=rub&dest=-1257786&nm={nm}"
)

_WB_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.wildberries.ru/",
    "Origin": "https://www.wildberries.ru",
}

_BASKET_THRESHOLDS = [
    (143, 1), (287, 2), (431, 3), (719, 4), (1007, 5),
    (1061, 6), (1115, 7), (1169, 8), (1313, 9), (1601, 10),
    (1655, 11), (1919, 12), (2045, 13), (2189, 14), (2405, 15),
    (2621, 16), (2837, 17), (3053, 18), (3269, 19), (3485, 20),
    (3701, 21), (3917, 22), (4133, 23), (4349, 24), (4565, 25),
]
_WB_IMG = "https://basket-{b:02d}.wbbasket.ru/vol{vol}/part{part}/{nm}/images/big/{i}.webp"


def _basket(vol: int) -> int:
    for threshold, b in _BASKET_THRESHOLDS:
        if vol <= threshold:
            return b
    return 26


def _image_urls(nm: int, n: int = 10) -> list:
    vol  = nm // 100000
    part = nm // 1000
    b    = _basket(vol)
    return [_WB_IMG.format(b=b, vol=vol, part=part, nm=nm, i=i) for i in range(1, n + 1)]


def _extract_nm(url: str):
    # Gérer les URLs doublées (bug scp.xlsx) ex: "https://...aspxhttps://...aspx"
    m = re.search(r"/catalog/(\d+)", url)
    return int(m.group(1)) if m else None


def _call_api(nm: int, session: requests.Session) -> dict:
    try:
        resp = session.get(_WB_API.format(nm=nm), headers=_WB_HEADERS, timeout=15)
        resp.raise_for_status()
        products = resp.json().get("data", {}).get("products", [])
        return products[0] if products else {}
    except Exception:
        return {}


def _parse_api(p: dict) -> dict:
    price_kopeek = p.get("salePriceU") or p.get("priceU") or 0
    prix = str(round(price_kopeek / 100, 2)) if price_kopeek else ""
    brand = p.get("brand") or p.get("brandName") or ""
    name  = p.get("name") or ""
    titre = f"{brand} {name}".strip() if name else ""
    nm = p.get("id") or 0
    media = p.get("mediaFiles") or []
    images = [m.get("fullSize") or m.get("value") or "" for m in media] if media else _image_urls(nm)
    images = [u for u in images if u]
    return {
        "titre": titre, "marque": brand, "prix": prix, "devise": "RUB",
        "description": (p.get("description") or "").strip()[:2000],
        "liens_images": images,
    }


# ---------------------------------------------------------------------------
# Playwright — délégué à playwright_manager (instance unique partagée)
# ---------------------------------------------------------------------------
from scrapers import playwright_manager as _pm


def _get_page():
    """Retourne la page Playwright WB via le manager partagé."""
    return _pm.get_wb_page()


def close_playwright():
    """Ferme le contexte WB. À appeler en fin de session main.py."""
    _pm.close_wb()


def _extract_images_from_html(html: str, nm: int) -> list:
    """Extrait les URLs images/big depuis le JSON embarqué dans la page WB."""
    pattern = re.compile(
        r'"(https://basket-\d+\.wbbasket\.ru/vol\d+/part\d+/'
        + str(nm) + r'/images/big/\d+\.webp)"'
    )
    urls = list(dict.fromkeys(pattern.findall(html)))
    if urls:
        return urls
    # Fallback : autres tailles → convertir en /big/
    pattern2 = re.compile(
        r'"(https://basket-\d+\.wbbasket\.ru/vol\d+/part\d+/'
        + str(nm) + r'/images/[^"]+\.webp)"'
    )
    raw = list(dict.fromkeys(pattern2.findall(html)))
    big_urls = []
    for u in raw:
        big = re.sub(r'/images/[^/]+/(\d+\.webp)$', r'/images/big/\1', u)
        if big not in big_urls:
            big_urls.append(big)
    return big_urls


def _scrape_with_playwright(url: str, nm: int) -> dict:
    """
    Navigue vers l'URL WB dans le navigateur persistant et extrait les données.
    Sélecteurs validés sur HTML réel WB (juillet 2025) :
      Titre  → [class*='productTitle']
      Marque → [class*='productNameBrand'] | [class*='productHeaderBrandText']
      Prix   → [class*='productLinePriceNow'] | [class*='priceBlockFinalPrice']
      Images → JSON embarqué dans le HTML
    """
    from playwright.sync_api import TimeoutError as PWTimeout

    result = {
        "titre": "", "marque": "", "prix": "",
        "devise": "RUB", "description": "", "liens_images": [],
    }

    page = _get_page()

    # Extraire le vrai nm de l'URL (au cas où l'URL est doublée)
    clean_url = f"https://www.wildberries.ru/catalog/{nm}/detail.aspx"

    print(f"  [WB] Playwright → {clean_url}")
    for nav_attempt in range(2):
        try:
            page.goto(clean_url, wait_until="domcontentloaded", timeout=60_000)
            break
        except PWTimeout:
            if nav_attempt == 0:
                print("  [WB] Timeout navigation — retry...")
                time.sleep(5)
            else:
                raise RuntimeError(f"Timeout navigation WB pour nm={nm}")

    # Détecter et gérer le captcha WB ("Подозрительная активность")
    # Après 2 tentatives infructueuses → abandon pour ne pas bloquer le run
    for attempt in range(2):
        try:
            page_text = page.inner_text("body") if page.query_selector("body") else ""
        except Exception:
            page_text = ""

        if "Подозрительная активность" in page_text or "Что-то не так" in page_text:
            if attempt == 1:
                raise RuntimeError(
                    f"Captcha WB persistant pour nm={nm} — produit ignoré, réessaie plus tard"
                )
            print(f"  [WB] Captcha — attente 90s avant retry...")
            time.sleep(90)
            try:
                page.reload(wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                pass
        else:
            break  # Pas de captcha → continuer

    try:
        page.wait_for_selector("[class*='productTitle']", timeout=20_000)
    except PWTimeout:
        print("  [WB] Timeout — tentative d'extraction quand même")

    # Pause humaine + délai anti-ban entre produits WB (important pour éviter le captcha)
    time.sleep(random.uniform(12, 20))
    html = page.content()

    # --- Parse ---
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    tag = soup.select_one("[class*='productTitle']")
    if tag:
        result["titre"] = tag.get_text(strip=True)

    tag = soup.select_one("[class*='productNameBrand'], [class*='productHeaderBrandText']")
    if tag:
        result["marque"] = tag.get_text(strip=True)

    tag = soup.select_one("[class*='productLinePriceNow'], [class*='priceBlockFinalPrice']")
    if tag:
        result["prix"] = parse_price(tag.get_text(strip=True))

    for sel in ["[class*='productDescription']", "[class*='collapsible-details']",
                "[class*='product-params']", "[class*='productComposition']"]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(" ", strip=True)
            if len(text) > 30:
                result["description"] = text[:2000]
                break

    result["liens_images"] = _extract_images_from_html(html, nm) or _image_urls(nm)
    return result


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def scrape(url: str, session) -> dict:
    nm = _extract_nm(url)
    if nm is None:
        raise RuntimeError("ID article introuvable dans l'URL")

    # Niveau 1 : API interne
    api_data = _call_api(nm, session)
    if api_data:
        print(f"  [WB] API ✓ pour nm={nm}")
        return _parse_api(api_data)

    # Niveau 2 : Playwright persistant
    print(f"  [WB] API vide pour nm={nm} → Playwright")
    try:
        result = _scrape_with_playwright(url, nm)
        if result["titre"]:
            return result
        raise RuntimeError("Playwright n'a pas pu extraire les données WB")
    except ImportError:
        raise RuntimeError(
            "Playwright non installé.\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )
    except Exception as exc:
        # Si la page/browser a été fermé(e), réinitialiser pour le prochain appel
        if "closed" in str(exc).lower() or "target" in str(exc).lower():
            print("  [WB] Navigateur fermé — réinitialisation au prochain appel")
            close_playwright()
        raise
