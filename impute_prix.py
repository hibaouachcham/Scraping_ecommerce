"""
Impute les prix manquants par la moyenne des autres sites du même produit.
Étapes :
  1. Convertir tous les prix en USD (taux approx.)
  2. Pour chaque produit avec prix vide, calculer la moyenne USD des autres sites
  3. Reconvertir en devise locale du site cible

Lance : python impute_prix.py
"""
import csv
from collections import defaultdict

CSV_PATH = "output/produits.csv"

# Taux de change approximatifs → USD (juillet 2025)
TO_USD = {
    "MAD": 1 / 10.0,    # 1 MAD ≈ 0.10 USD
    "RUB": 1 / 88.0,    # 1 RUB ≈ 0.011 USD
    "AED": 1 / 3.67,    # 1 AED = 0.272 USD (parité fixe)
    "PKR": 1 / 278.0,   # 1 PKR ≈ 0.0036 USD
    "USD": 1.0,
}
FROM_USD = {dev: 1 / rate for dev, rate in TO_USD.items()}

def to_usd(prix_str, devise):
    try:
        val = float(prix_str)
        return val * TO_USD.get(devise, 1.0)
    except (ValueError, TypeError):
        return None

def from_usd(usd_val, devise):
    return round(usd_val * FROM_USD.get(devise, 1.0), 2)

# Charger le CSV
with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    fieldnames = reader.fieldnames
    rows = list(reader)

# Indexer par id : {id → {site → row}}
by_product = defaultdict(dict)
for row in rows:
    if row.get("statut_scraping") == "ok":
        by_product[str(row["id"])][row["site"]] = row

# Imputer les prix manquants
imputed = 0
for pid, sites in by_product.items():
    for site, row in sites.items():
        if row.get("prix", "").strip():
            continue  # prix déjà présent

        devise = row.get("devise", "")
        # Collecter les prix USD des autres sites pour le même produit
        usd_prices = []
        for other_site, other_row in sites.items():
            if other_site == site:
                continue
            p = other_row.get("prix", "").strip()
            d = other_row.get("devise", "")
            if p and d:
                usd = to_usd(p, d)
                if usd:
                    usd_prices.append(usd)

        if not usd_prices:
            continue

        avg_usd = sum(usd_prices) / len(usd_prices)
        prix_imputé = from_usd(avg_usd, devise)

        row["prix"] = str(prix_imputé)
        print(f"  {row['row_id']:25s} | devise={devise:3s} | "
              f"avg_usd={avg_usd:.2f} → prix imputé={prix_imputé} {devise} "
              f"(basé sur {len(usd_prices)} site(s))")
        imputed += 1

# Sauvegarder
with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";",
                            quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    writer.writerows(rows)

print(f"\n{imputed} prix imputés par moyenne des autres sites.")
print("Taux utilisés :")
for dev, rate in TO_USD.items():
    print(f"  1 {dev} = {rate:.4f} USD")
