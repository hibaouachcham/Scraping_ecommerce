"""
Réorganise produits.csv pour grouper les 4 sites par produit :
  id=0 jumia → id=0 wildberries → id=0 trendyol → id=0 daraz
  id=1 jumia → id=1 wildberries → id=1 trendyol → id=1 daraz
  ...

Lance APRÈS la fin du scraping complet :
  python sort_csv.py
"""
import csv

INPUT  = "output/produits.csv"
OUTPUT = "output/produits.csv"  # réécrit en place

SITE_ORDER = {"jumia": 0, "wildberries": 1, "trendyol": 2, "daraz": 3}

with open(INPUT, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    fieldnames = reader.fieldnames
    rows = list(reader)

# Tri : d'abord par id numérique, ensuite par ordre de site
rows.sort(key=lambda r: (
    int(r["id"]) if str(r["id"]).isdigit() else 9999,
    SITE_ORDER.get(r["site"], 99),
))

with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";",
                            quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    writer.writerows(rows)

print(f"Trié : {len(rows)} lignes → groupées par produit (4 sites consécutifs)")
