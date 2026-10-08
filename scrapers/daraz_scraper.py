"""
Scraper pour Daraz (daraz.pk).

Daraz (groupe Lazada/Alibaba) charge les prix via JavaScript.
Stratégie :
  1. JSON-LD (server-rendered) → titre, marque, images
  2. Playwright → prix + données manquantes

Sélecteurs Daraz (juillet 2025) :
  Titre  : [class*='pdp-mod-product-badge-title']  ou  h1
  Prix   : [class*='pdp-price']  ou  span.notranslate
  Marque : [class*='pdp-product-brand']
  Images : JSON-LD contentUrl (déjà server-rendered)
"""
import re
from bs4 import BeautifulSoup

from utils import (
    extract_jsonld_products, normalize_images, parse_price, fetch
)
from scrapers import playwright_manager as pm


def scrape(url: str, session) -> dict:
    result = {
        "titre": "", "marque": "", "prix": "",
        "devise": "PKR", "description": "", "liens_images": [],
    }

    # Niveau 1 : requests (JSON-LD server-rendered pour titre + images)
    resp = fetch(url, session)
    if resp:
        soup_static = BeautifulSoup(resp.text, "lxml")
        products = extract_jsonld_products(soup_static)
        if products:
            p = products[0]
            result["titre"] = p.get("name", "") or ""
            brand = p.get("brand")
            result["marque"] = (brand.get("name") if isinstance(brand, dict) else brand or "") or ""
            result["liens_images"] = normalize_images(p.get("image"))
            # Prix dans JSON-LD (souvent absent sur Daraz)
            offers = p.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0]
            result["prix"] = parse_price(offers.get("price") or offers.get("lowPrice"))
            result["devise"] = offers.get("priceCurrency", "PKR") or "PKR"

    # Niveau 2 : Playwright pour le prix (et les données manquantes)
    if not result["prix"] or not result["titre"]:
        html = pm.navigate(
            url,
            wait_selector="[class*='pdp-price_type_normal'], [class*='pdp-mod-product-badge-title'], h1",
            timeout=30_000,
        )
        soup = BeautifulSoup(html, "lxml")

        # Titre
        if not result["titre"]:
            for sel in ["[class*='pdp-mod-product-badge-title']",
                        "[class*='product-title']", "h1"]:
                tag = soup.select_one(sel)
                if tag:
                    result["titre"] = tag.get_text(strip=True)
                    break

        # Marque
        if not result["marque"]:
            for sel in ["[class*='pdp-product-brand']", "[class*='brand']"]:
                tag = soup.select_one(sel)
                if tag:
                    text = tag.get_text(strip=True)
                    if text:
                        result["marque"] = text
                        break

        # Prix — find() avec lambda (plus fiable que CSS sur multi-classes)
        if not result["prix"]:
            # Chercher span avec pdp-price_type_normal (prix actuel, pas le barré)
            tag = soup.find(
                "span",
                class_=lambda c: c and "pdp-price_type_normal" in " ".join(c)
            )
            if tag:
                result["prix"] = parse_price(tag.get_text(strip=True))

        # Fallback CSS si find() a échoué
        if not result["prix"]:
            for sel in ["span.pdp-price", "[class*='pdp-mod-product-price'] span"]:
                tag = soup.select_one(sel)
                if tag:
                    result["prix"] = parse_price(tag.get_text(strip=True))
                    if result["prix"]:
                        break

        # Fallback regex sur le HTML brut (cherche prix normal avant prix barré)
        if not result["prix"]:
            import re as _re
            # pdp-price_type_normal dans le HTML → extraire le prix juste après
            m = _re.search(r'pdp-price_type_normal[^>]*>(Rs\.?\s*[\d,]+)', html)
            if not m:
                m = _re.search(r'(?:Rs\.?\s*|PKR\s*)([\d,]+)', html)
            if m:
                raw = m.group(1)
                result["prix"] = parse_price(raw.replace("Rs.", "").replace("Rs", "").strip())

        # Description
        if not result["description"]:
            for sel in ["[class*='pdp-product-desc']", "[class*='pdp-mod-section']",
                        "[class*='detail-content']"]:
                tag = soup.select_one(sel)
                if tag:
                    text = tag.get_text(" ", strip=True)
                    if len(text) > 20:
                        result["description"] = text[:2000]
                        break

        # Images si absentes du JSON-LD
        if not result["liens_images"]:
            seen = set()
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if "daraz" in src or "lazada" in src or "alicdn" in src:
                    if src not in seen and any(
                        ext in src for ext in [".jpg", ".jpeg", ".png", ".webp"]
                    ):
                        seen.add(src)
                        result["liens_images"].append(src)

    return result
