"""
Télécharge les images des produits depuis produits.csv.

Structure de sortie :
  output/images/{site}/{id_produit}/image_1.jpg
                                    image_2.jpg
                                    ...

Lance : python download_images.py
Options :
  --site jumia          → télécharger seulement un site
  --id 5                → télécharger seulement un produit
  --workers 4           → nombre de threads (défaut: 4)
  --resume              → ignorer les dossiers déjà complets (défaut: True)
"""

import csv
import os
import time
import argparse
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

CSV_PATH   = "output/produits.csv"
IMAGES_DIR = Path("output/images")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

# Extension par défaut si non détectable depuis l'URL
DEFAULT_EXT = ".jpg"


def get_ext(url: str) -> str:
    """Extrait l'extension depuis l'URL (.jpg, .png, .webp, .jpeg)."""
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ext
    return DEFAULT_EXT


def download_one(url: str, dest: Path, retries: int = 3) -> bool:
    """Télécharge une image vers dest. Retourne True si succès."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20, stream=True)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # backoff: 1s, 2s
            else:
                print(f"    ✗ Échec ({e}) : {url}")
                return False
    return False


def parse_images(liens_str: str) -> list[str]:
    """Convertit la colonne liens_images (séparateur '|' ou ',' ou ' ') en liste."""
    if not liens_str or not liens_str.strip():
        return []
    # Essayer les séparateurs dans l'ordre
    for sep in ["|", ","]:
        if sep in liens_str:
            return [u.strip() for u in liens_str.split(sep) if u.strip()]
    return [liens_str.strip()]


def load_tasks(filter_site=None, filter_id=None):
    """Charge le CSV et retourne la liste des tâches de téléchargement."""
    tasks = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row.get("statut_scraping") != "ok":
                continue
            site = row.get("site", "").strip()
            pid  = row.get("id", "").strip()
            liens = parse_images(row.get("liens_images", ""))

            if not site or not pid or not liens:
                continue
            if filter_site and site != filter_site:
                continue
            if filter_id and pid != str(filter_id):
                continue

            tasks.append({
                "site":  site,
                "id":    pid,
                "urls":  liens,
            })
    return tasks


def download_product(task: dict, resume: bool) -> dict:
    """Télécharge toutes les images d'un produit. Retourne un rapport."""
    site   = task["site"]
    pid    = task["id"]
    urls   = task["urls"]
    folder = IMAGES_DIR / site / pid

    ok = 0
    skip = 0
    fail = 0

    for i, url in enumerate(urls, start=1):
        ext  = get_ext(url)
        dest = folder / f"image_{i}{ext}"

        if resume and dest.exists() and dest.stat().st_size > 0:
            skip += 1
            continue

        success = download_one(url, dest)
        if success:
            ok += 1
        else:
            fail += 1

    return {"site": site, "id": pid, "ok": ok, "skip": skip, "fail": fail}


def main():
    parser = argparse.ArgumentParser(description="Télécharge les images produits.")
    parser.add_argument("--site",    help="Filtrer par site (jumia, wildberries, trendyol, daraz)")
    parser.add_argument("--id",      help="Filtrer par id produit")
    parser.add_argument("--workers", type=int, default=4, help="Threads parallèles (défaut: 4)")
    parser.add_argument("--no-resume", action="store_true", help="Re-télécharger même si déjà présent")
    args = parser.parse_args()

    resume = not args.no_resume

    tasks = load_tasks(filter_site=args.site, filter_id=args.id)
    print(f"{len(tasks)} produit(s) à traiter — {args.workers} thread(s)"
          f"{' — resume activé' if resume else ''}\n")

    total_ok = total_skip = total_fail = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_product, t, resume): t
            for t in tasks
        }
        done = 0
        for future in as_completed(futures):
            result = future.result()
            done += 1
            total_ok   += result["ok"]
            total_skip += result["skip"]
            total_fail += result["fail"]
            status = f"✓ {result['ok']} img"
            if result["skip"]:
                status += f"  (skip {result['skip']})"
            if result["fail"]:
                status += f"  ✗ {result['fail']} échec(s)"
            print(f"  [{done:3d}/{len(tasks)}] {result['site']:12s} id={result['id']:4s} — {status}")

    print(f"\n{'='*55}")
    print(f"  Téléchargées : {total_ok}")
    print(f"  Ignorées     : {total_skip}  (déjà présentes)")
    print(f"  Échecs       : {total_fail}")
    print(f"  Dossier      : {IMAGES_DIR.resolve()}")


if __name__ == "__main__":
    main()
