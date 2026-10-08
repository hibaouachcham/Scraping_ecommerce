"""
Fonctions utilitaires partagées par tous les scrapers.
"""
import json
import random
import re
import time

import requests
from bs4 import BeautifulSoup

# Liste de User-Agents à faire tourner pour limiter le risque de blocage.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
    "Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def get_session() -> requests.Session:
    """Crée une session requests avec des headers Chrome complets (anti-403 Cloudflare)."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;"
                      "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "sec-ch-ua": '"Chromium";v="125", "Google Chrome";v="125", "Not.A/Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Cache-Control": "max-age=0",
        }
    )
    return session


def polite_delay(min_s: float = 5.0, max_s: float = 10.0) -> None:
    """Pause aléatoire entre deux requêtes pour ne pas se faire bannir."""
    time.sleep(random.uniform(min_s, max_s))


def fetch(url: str, session: requests.Session, retries: int = 3, timeout: int = 20):
    """
    Récupère une page avec retries + backoff.
    Renvoie l'objet Response, ou None si toutes les tentatives échouent.
    """
    last_error = None
    for attempt in range(1, retries + 1):
        # Rotation du User-Agent à chaque tentative
        session.headers["User-Agent"] = random.choice(USER_AGENTS)
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code == 200:
                return resp
            last_error = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < retries:
            time.sleep(2 * attempt)  # backoff progressif

    print(f"[ECHEC] {url} -> {last_error}")
    return None


def extract_jsonld_products(soup: BeautifulSoup):
    """
    Cherche les blocs <script type="application/ld+json"> et renvoie
    la liste des objets dont @type == "Product".
    Beaucoup de sites e-commerce embarquent ces données structurées
    pour le SEO -> plus fiable que de parser le HTML visuel.
    """
    products = []
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        # Construire une liste plate de tous les noeuds a inspecter
        # (evite de modifier la liste pendant l iteration)
        nodes = data if isinstance(data, list) else [data]
        flat = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                flat.extend(g for g in graph if isinstance(g, dict))
            else:
                flat.append(node)

        for item in flat:
            if item.get("@type") in ("Product", ["Product"]):
                products.append(item)
    return products


def parse_price(raw_price) -> str:
    """
    Nettoie un prix (str ou nombre) en une chaîne numérique simple.
    Gère les formats européens (3.499,00 → 3499.00) et l'espace insécable.
    """
    if raw_price is None:
        return ""
    text = str(raw_price).replace("\xa0", " ").strip()

    # Format européen : séparateur de milliers = point, décimale = virgule
    # Ex : "3.499,00" → "3499.00"
    if re.search(r"\d\.\d{3},\d{2}", text):
        text = text.replace(".", "").replace(",", ".")

    match = re.search(r"[\d\s.,]+", text)
    if not match:
        return ""
    number = match.group(0).replace(" ", "")

    # Virgule ET point : détecter l'ordre pour trouver le séparateur de milliers
    if "," in number and "." in number:
        comma_pos = number.index(",")
        dot_pos   = number.index(".")
        if comma_pos < dot_pos:
            # Format anglais : 1,322.99 → virgule = milliers → supprimer
            number = number.replace(",", "")
        else:
            # Format européen : 1.322,99 → point = milliers → supprimer, virgule → point
            number = number.replace(".", "").replace(",", ".")

    # Virgule seule comme décimale (ex: "1299,99")
    elif "," in number and "." not in number:
        if re.match(r"^\d+,\d{1,2}$", number):
            number = number.replace(",", ".")
        else:
            number = number.replace(",", "")

    # Garder seulement le premier point décimal
    parts = number.split(".")
    if len(parts) > 2:
        number = "".join(parts[:-1]) + "." + parts[-1]

    try:
        float(number)
        return number
    except ValueError:
        return ""


def normalize_images(image_field) -> list:
    """Uniformise le champ 'image' du JSON-LD (str, list, ou dict) en liste d'URLs."""
    if image_field is None:
        return []
    if isinstance(image_field, str):
        return [image_field]
    if isinstance(image_field, dict):
        url = image_field.get("url") or image_field.get("contentUrl")
        if not url:
            return []
        # contentUrl peut être une liste (cas Jumia : {"contentUrl": ["url1", "url2", ...]})
        if isinstance(url, list):
            return normalize_images(url)
        return [url]
    if isinstance(image_field, list):
        urls = []
        for item in image_field:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                url = item.get("url") or item.get("contentUrl")
                if url:
                    # url peut aussi être une liste
                    if isinstance(url, list):
                        urls.extend(u for u in url if isinstance(u, str) and u)
                    else:
                        urls.append(url)
        return urls
    return []
