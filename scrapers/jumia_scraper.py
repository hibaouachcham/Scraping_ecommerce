"""
Scraper pour Jumia (jumia.ma).
Strategie : pas de JSON-LD Product sur jumia.ma -> 100% selecteurs CSS.

Selecteurs verifies sur page reelle (juillet 2025) :
  - Titre   : h1.-fs20.-ptm.-pbxs
  - Prix    : span.-b.-ubpt.-tal.-fs24  (contient "379.00 Dhs")
  - Marque  : attribut data-ga4-item-brand sur le bouton wishlist [data-sku]
  - Images  : #imgs img.-fw.-fh  ->  attribut data-src  (deja en 500x500)
  - Description : div.markup
"""
from bs4 import BeautifulSoup

from utils import extract_jsonld_products, fetch, normalize_images, parse_price


def scrape(url: str, session) -> dict:
    """
    Scrape une page produit Jumia.
    Renvoie un dict avec les champs attendus, ou leve une exception
    si la page n'a pas pu etre recuperee (geree par l'appelant).
    """
    resp = fetch(url, session)
    if resp is None:
        raise RuntimeError("page inaccessible")

    soup = BeautifulSoup(resp.text, "lxml")

    result = {
        "titre": "",
        "marque": "",
        "prix": "",
        "devise": "MAD",
        "description": "",
        "liens_images": [],
    }

    # --- 1. Tentative via JSON-LD (au cas ou une page l'aurait) ---
    products = extract_jsonld_products(soup)
    if products:
        data = products[0]
        result["titre"] = data.get("name", "") or ""

        brand = data.get("brand")
        if isinstance(brand, dict):
            result["marque"] = brand.get("name", "") or ""
        elif isinstance(brand, str):
            result["marque"] = brand

        result["description"] = (data.get("description") or "").strip()
        result["liens_images"] = normalize_images(data.get("image"))

        offers = data.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            result["prix"] = parse_price(offers.get("price"))
            result["devise"] = offers.get("priceCurrency", "MAD") or "MAD"

    # --- 2. Selecteurs CSS (verifies sur jumia.ma, juillet 2025) ---

    # Titre : <h1 class="-fs20 -ptm -pbxs">
    if not result["titre"]:
        tag = soup.select_one("h1.-fs20, h1.-fs22, h1")
        if tag:
            result["titre"] = tag.get_text(strip=True)

    # Prix : <span class="-b -ubpt -tal -fs24 -prxs">379.00 Dhs</span>
    if not result["prix"]:
        tag = soup.select_one("span.-b.-ubpt.-tal.-fs24")
        if tag:
            result["prix"] = parse_price(tag.get_text(strip=True))

    # Marque : attribut data-ga4-item-brand sur le bouton wishlist
    if not result["marque"]:
        tag = soup.find(attrs={"data-ga4-item-brand": True})
        if tag:
            result["marque"] = tag["data-ga4-item-brand"].strip()

    # Description : <div class="markup">
    if not result["description"]:
        tag = soup.select_one("div.markup, div.-pvs.-lsn")
        if tag:
            result["description"] = " ".join(tag.get_text(" ", strip=True).split())[:2000]

    # Images : chercher tous les img[data-src] contenant une URL produit 500x500.
    # On filtre les thumbnails (150x150) et les bannieres pub (cms/).
    if not result["liens_images"]:
        urls = []
        for img in soup.find_all("img", attrs={"data-src": True}):
            src = img["data-src"]
            if "500x500" in src and "/product/" in src and src not in urls:
                urls.append(src)
        # Fallback : prendre les hrefs des liens galerie (680x680)
        if not urls:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "680x680" in href and "/product/" in href and href not in urls:
                    urls.append(href)
        result["liens_images"] = urls

    return result
