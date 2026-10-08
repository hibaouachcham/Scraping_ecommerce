"""
Remplit les colonnes categorie et sous_categorie dans produits.csv.
Lance : python fill_categories.py
"""
import csv

CSV_PATH = "output/produits.csv"

# Mapping id produit → (categorie, sous_categorie)
CATEGORIES = {}

ranges = [
    (range(0,  22), "Electronique",               "Smartphones"),
    (range(22, 31), "Electronique",               "Casques audio & Écouteurs"),
    (range(31, 38), "Beauté & Cosmétiques",        "Parfums"),
    (range(38, 48), "Beauté & Cosmétiques",        "Produits cosmétiques"),
    (range(48, 50), "Mode & Sport",                "Chaussures"),
    (range(50, 56), "Electronique",               "Tablettes"),
    (range(56, 57), "Electronique",               "Powerbanks"),
    (range(57, 73), "Accessoires & Mode",          "Montres"),
    (range(73, 75), "Electronique",               "Télécommandes"),
    (range(75, 77), "Electronique",               "Chargeurs"),
    (range(77, 84), "Informatique",               "Souris"),
    (range(84, 89), "Informatique",               "Clés USB"),
    (range(89, 95), "Gaming & Jeux vidéo",         "Manettes de jeux"),
    (range(95, 99), "Sécurité & Maison connectée", "Caméras surveillance Wi-Fi"),
    (range(99, 102), "Informatique",               "Webcams"),

    # Nouveaux produits
    (range(101, 104), "Électroménager",             "Bouilloires électriques"),
    (range(104, 108), "Électroménager",             "Air Fryers"),
    (range(108, 119), "Électroménager",             "Machines à café"),
    (range(119, 124), "Mode & Accessoires",         "Lunettes"),
    (range(124, 128), "Electronique",               "Appareils photo"),
    (range(128, 131), "Beauté & Soins personnels",  "Lisseurs"),
    (range(131, 139), "Beauté & Soins personnels",  "Sèche-cheveux"),
    (range(139, 146), "Beauté & Soins personnels",  "Tondeuses"),
    (range(146, 150), "Électroménager",             "Aspirateurs"),
    (range(150, 154), "Beauté & Soins personnels",  "Brosses à dents électriques"),
    (range(154, 155), "Électroménager",             "Ventilateurs"),
    (range(155, 159), "Beauté & Soins personnels",  "Brosses"),
    (range(159, 167), "Electronique",               "Bracelets connectés"),
    (range(167, 171), "Beauté & Soins personnels",  "Boucleurs"),
    (range(171, 179), "Mode & Accessoires",         "Sacs"),
    (range(179, 182), "Mode & Accessoires",         "Sacs à dos"),
    (range(182, 192), "Informatique",               "SSD externes"),
    (range(192, 209), "Informatique",               "Routeurs Wi-Fi"),
    (range(209, 218), "Informatique",               "Imprimantes"),
    (range(218, 222), "Electronique",               "Mini projecteurs"),
    (range(222, 225), "Electronique",               "Box Android TV"),
    (range(225, 231), "Mode & Sport",               "Chaussures"),
    (range(231, 235), "Electronique",               "Powerbanks"),
    (range(235, 239), "Santé & Bien-être",          "Tensiomètres"),
]

for rng, cat, sous_cat in ranges:
    for i in rng:
        CATEGORIES[i] = (cat, sous_cat)

# Charger et mettre à jour le CSV
with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    fieldnames = reader.fieldnames
    rows = list(reader)

updated = 0
for row in rows:
    try:
        pid = int(row["id"])
    except (ValueError, TypeError):
        continue
    if pid in CATEGORIES:
        cat, sous_cat = CATEGORIES[pid]
        row["categorie"]     = cat
        row["sous_categorie"] = sous_cat
        updated += 1

with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";",
                            quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    writer.writerows(rows)

print(f"{updated} lignes mises à jour.")
print("\nRécapitulatif :")
for rng, cat, sous_cat in ranges:
    n = len(rng) * 4  # 4 sites par produit
    print(f"  ids {rng.start:3d}-{rng.stop-1:3d} | {cat:30s} | {sous_cat}")
