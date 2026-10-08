"""
Phase 1 : scraping des métadonnées produit (Jumia + Wildberries)
à partir du fichier scp.xlsx, écriture incrémentale dans un CSV.

Usage :
    python main.py

Fichiers attendus :
    input/scp.xlsx   -> ton fichier avec les colonnes id, JUMIA, WILDBERRIES,
                         TRENDYOL, DARAZ et les lignes "Categorie X : ..."
Sortie :
    output/produits.csv
"""
import csv
import os
import re

import openpyxl

from scrapers import jumia_scraper, wildberries_scraper, trendyol_scraper, daraz_scraper
from scrapers.wildberries_scraper import close_playwright
from scrapers import playwright_manager as playwright_manager
from utils import get_session, polite_delay

INPUT_XLSX = "input/scp.xlsx"
OUTPUT_CSV = "output/produits.csv"

SITES_A_TRAITER = {
    "jumia":        {"colonne": "B", "scraper": jumia_scraper},
    "wildberries":  {"colonne": "C", "scraper": wildberries_scraper},
    "trendyol":     {"colonne": "D", "scraper": trendyol_scraper},
    "daraz":        {"colonne": "E", "scraper": daraz_scraper},
}

CSV_FIELDNAMES = [
    "id",
    "site",
    "row_id",
    "lien",
    "titre",
    "marque",
    "categorie",
    "sous_categorie",
    "prix",
    "devise",
    "description",
    "liens_images",
    "nb_images",
    "statut_scraping",
]

CATEGORIE_PATTERN = re.compile(r"Categorie\s*\d*\s*[:\-]?\s*(.+)", re.IGNORECASE)


def read_products(path):
    """
    Parcourt le fichier scp.xlsx et yield un dict par produit :
    {"id": ..., "categorie": ..., "jumia": url_ou_None, "wildberries": url_ou_None, ...}
    Détecte automatiquement les lignes "Categorie X : ..." pour mettre à jour
    la catégorie courante.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    current_categorie = ""
    for row in ws.iter_rows(min_row=2):
        values = [cell.value for cell in row[:5]]  # colonnes A à E
        id_val, jumia, wildberries, trendyol, daraz = (values + [None] * 5)[:5]

        # Ligne "Categorie X : xxx" -> toutes les cellules texte contiennent
        # souvent la même info à cause de la fusion. On la détecte via regex.
        row_text = " ".join(str(v) for v in values if v)
        match = CATEGORIE_PATTERN.search(row_text)
        if match and id_val is None:
            current_categorie = match.group(1).strip()
            continue

        # Ligne d'en-tête ("id", "JUMIA", ...) ou ligne vide -> on ignore
        if id_val is None or str(id_val).strip().lower() == "id":
            continue

        yield {
            "id": id_val,
            "categorie": current_categorie,
            "jumia": jumia,
            "wildberries": wildberries,
            "trendyol": trendyol,
            "daraz": daraz,
        }


def load_ok_rows(path):
    """
    Lit le CSV existant et retourne :
      - done : ensemble des row_id avec statut 'ok' (a skipper)
      - ok_rows : liste des dicts de ces lignes (pour reecriture propre)
    """
    done = set()
    ok_rows = []
    if not os.path.exists(path):
        return done, ok_rows
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row.get("statut_scraping") == "ok":
                done.add(row["row_id"])
                ok_rows.append(dict(row))
    return done, ok_rows


def main(limit=None):
    os.makedirs("output", exist_ok=True)

    # Charger les lignes ok existantes, puis réécrire le CSV proprement
    # (supprime les doublons et les anciennes lignes erreur)
    already_done, ok_rows = load_ok_rows(OUTPUT_CSV)

    session = get_session()

    SESSIONS = {
        "jumia": session,
        "wildberries": session,
        "trendyol": session,
        "daraz": session,
    }

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=CSV_FIELDNAMES, delimiter=";", quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        # Réécrire les lignes ok déjà acquises
        for row in ok_rows:
            writer.writerow(row)
        f.flush()

        products = read_products(INPUT_XLSX)
        if limit:
            import itertools
            products = itertools.islice(products, limit)
        for product in products:
            pid = product["id"]
            print(f"[PRODUIT] id={pid} | jumia={bool(product.get('jumia'))} | wb={bool(product.get('wildberries'))}")

            for site_name, cfg in SITES_A_TRAITER.items():
                url = product.get(site_name)
                if not url:
                    continue  # pas de lien pour ce site sur ce produit

                row_id = f"{pid}_{site_name}"
                if row_id in already_done:
                    print(f"[SKIP] {row_id} déjà fait")
                    continue

                print(f"[SCRAPING] {row_id} -> {url}")
                row = {
                    "id": pid,
                    "site": site_name,
                    "row_id": row_id,
                    "lien": url,
                    "titre": "",
                    "marque": "",
                    "categorie": product["categorie"],
                    "sous_categorie": "",
                    "prix": "",
                    "devise": "",
                    "description": "",
                    "liens_images": "",
                    "nb_images": 0,
                    "statut_scraping": "erreur",
                }

                try:
                    data = cfg["scraper"].scrape(url, SESSIONS.get(site_name, session))
                    row["titre"] = data.get("titre", "")
                    row["marque"] = data.get("marque", "")
                    row["prix"] = data.get("prix", "")
                    row["devise"] = data.get("devise", "")
                    row["description"] = data.get("description", "")
                    images = data.get("liens_images", [])
                    # Securite : s'assurer que chaque element est une chaine
                    images = [str(u) for u in images if isinstance(u, str) and u]
                    row["liens_images"] = "|".join(images)
                    row["nb_images"] = len(images)
                    row["statut_scraping"] = "ok"
                except Exception as exc:  # noqa: BLE001
                    print(f"  -> échec : {exc}")
                    row["statut_scraping"] = f"erreur: {exc}"

                writer.writerow(row)
                f.flush()  # écriture immédiate sur disque -> pas de perte en cas de crash

                polite_delay()  # pause entre chaque requête

    # Fermer les navigateurs Playwright proprement
    playwright_manager.close_all()  # Ferme tout (WB + Trendyol + Daraz)
    print("Terminé.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Limite le nombre de lignes de scp.xlsx (test)")
    args = parser.parse_args()
    main(limit=args.limit)
