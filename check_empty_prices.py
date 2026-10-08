"""
Compte les produits avec prix vide par site.
Lance : python check_empty_prices.py
"""
import csv
from collections import defaultdict

CSV_PATH = "output/produits.csv"

with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    rows = list(reader)

empty_by_site = defaultdict(list)
for row in rows:
    if row.get("statut_scraping") == "ok" and not row.get("prix", "").strip():
        empty_by_site[row["site"]].append(row["row_id"])

print("=== Prix vides par site (statut=ok) ===")
total = 0
for site, ids in sorted(empty_by_site.items()):
    print(f"  {site}: {len(ids)} produits")
    for rid in ids[:5]:
        print(f"    {rid}")
    if len(ids) > 5:
        print(f"    ... et {len(ids)-5} autres")
    total += len(ids)
print(f"\nTotal : {total} produits sans prix")
