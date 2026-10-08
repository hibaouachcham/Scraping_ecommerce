"""
Vérifie la qualité des images scrapées par site.
Lance : python check_images.py
"""
import csv
from collections import defaultdict

CSV_PATH = "output/produits.csv"

with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    rows = [r for r in csv.DictReader(f, delimiter=";")
            if r.get("statut_scraping") == "ok"]

stats = defaultdict(lambda: {"total": 0, "zero_img": [], "bad_img": [], "nb_imgs": []})

DOMAINES_SUSPECTS = ["cookielaw", "onetrust", "placeholder", "no-image", "noimage"]

for row in rows:
    site = row["site"]
    nb   = int(row.get("nb_images") or 0)
    imgs = [u.strip() for u in row.get("liens_images", "").split("|") if u.strip()]

    stats[site]["total"] += 1
    stats[site]["nb_imgs"].append(nb)

    if nb == 0 or not imgs:
        stats[site]["zero_img"].append(row["row_id"])
    else:
        # Vérifier les URLs suspectes
        bad = [u for u in imgs if any(d in u for d in DOMAINES_SUSPECTS)]
        if bad:
            stats[site]["bad_img"].append((row["row_id"], bad[0]))

print("=" * 60)
print("RAPPORT IMAGES PAR SITE")
print("=" * 60)
for site in ["jumia", "wildberries", "trendyol", "daraz"]:
    s = stats[site]
    if s["total"] == 0:
        continue
    nb_list = s["nb_imgs"]
    avg = sum(nb_list) / len(nb_list) if nb_list else 0
    mn  = min(nb_list) if nb_list else 0
    mx  = max(nb_list) if nb_list else 0
    print(f"\n{site.upper()} ({s['total']} produits)")
    print(f"  Images/produit : avg={avg:.1f}  min={mn}  max={mx}")
    if s["zero_img"]:
        print(f"  ⚠ 0 image     : {len(s['zero_img'])} produits → {s['zero_img'][:5]}")
    else:
        print(f"  ✓ 0 image     : aucun")
    if s["bad_img"]:
        print(f"  ⚠ URL suspecte: {len(s['bad_img'])} produits")
        for rid, url in s["bad_img"][:3]:
            print(f"      {rid} → {url[:70]}")
    else:
        print(f"  ✓ URL suspecte: aucune")

print("\n" + "=" * 60)
total_ok = sum(s["total"] for s in stats.values())
total_zero = sum(len(s["zero_img"]) for s in stats.values())
total_bad  = sum(len(s["bad_img"])  for s in stats.values())
print(f"TOTAL : {total_ok} lignes ok | {total_zero} sans image | {total_bad} URL suspecte")
