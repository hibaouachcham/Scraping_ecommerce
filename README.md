# Scraping Multi-Plateforme pour la Résolution d'Entités Visuelles en E-commerce

## Contexte du projet

Ce module fait partie d'un **Projet de Fin d'Année (PFA)** portant sur la **résolution d'entités visuelles dans le domaine du e-commerce**. L'objectif global est de détecter si deux fiches produits issues de plateformes différentes correspondent au même article réel, en s'appuyant principalement sur les images et les métadonnées.

Pour alimenter ce système, il est nécessaire de constituer un jeu de données multi-sources : les mêmes produits référencés sur plusieurs plateformes e-commerce avec leurs métadonnées et leurs images. C'est le rôle de ce module de scraping.

---

## Division de la tâche de scraping

La tâche de collecte de données a été divisée en **deux sous-tâches distinctes**, chacune avec des outils et des contraintes différents.

### Tâche 1 — Collecte des métadonnées produits

**Objectif :** Extraire, pour chaque produit et chaque plateforme, les champs textuels et les URLs des images, et les centraliser dans un fichier CSV structuré.

**Champs collectés :**

| Colonne | Description |
|---|---|
| `id` | Identifiant unique du produit (0 à 101) |
| `site` | Plateforme source (jumia, wildberries, trendyol, daraz) |
| `row_id` | Identifiant composite `{site}_{id}` |
| `lien` | URL de la fiche produit |
| `titre` | Nom du produit |
| `marque` | Marque / fabricant |
| `categorie` | Catégorie principale |
| `sous_categorie` | Sous-catégorie |
| `prix` | Prix numérique |
| `devise` | Devise (MAD, RUB, AED, PKR) |
| `description` | Description textuelle |
| `liens_images` | URLs des images, séparées par `\|` |
| `nb_images` | Nombre d'images disponibles |
| `statut_scraping` | `ok` ou message d'erreur |

**Résultat :** `output/produits.csv` — **404 lignes** (101 produits × 4 sites), toutes au statut `ok`.

**Pourquoi une tâche séparée ?** La collecte des métadonnées est une étape légère et rapide (requêtes HTTP + parsing HTML). Elle peut être relancée ou corrigée indépendamment du téléchargement des images, qui est long et coûteux en bande passante.

---

### Tâche 2 — Téléchargement des images

**Objectif :** Télécharger localement toutes les images référencées dans `produits.csv`, en les organisant selon une structure de dossiers cohérente avec l'objectif de résolution d'entités.

**Structure de dossiers :**

```
output/images/
├── jumia/
│   ├── 0/
│   │   ├── image_1.jpg
│   │   ├── image_2.jpg
│   │   └── ...
│   ├── 1/
│   └── ...
├── wildberries/
│   ├── 0/
│   └── ...
├── trendyol/
│   └── ...
└── daraz/
    └── ...
```

Chaque image est nommée `image_N.ext` où `N` est l'index dans la liste d'images du produit et `ext` est l'extension réelle détectée depuis l'URL (`.jpg`, `.webp`, `.png`...).

**Pourquoi cette structure ?** Regrouper les images par site puis par produit permet de :
- Charger facilement toutes les images d'un site pour l'extraction de features
- Comparer les images du même produit (`images/{site}/42/`) entre sites pour la résolution d'entités
- Ajouter un nouveau site sans modifier l'organisation existante

**Pourquoi une tâche séparée ?** Le téléchargement de centaines d'images est une opération longue qui dépend de la disponibilité des CDN externes. La séparer de la collecte des métadonnées permet de : relancer uniquement les images manquantes (option `--resume`), filtrer par site ou par produit, et éviter de tout re-scraper en cas d'interruption réseau.

---

## Périmètre des données

| Plateforme | Pays | Devise | Type d'accès |
|---|---|---|---|
| Jumia (jumia.ma) | Maroc | MAD | Requêtes HTTP classiques |
| Wildberries (wildberries.ru) | Russie | RUB | Playwright (SPA React) |
| Trendyol (trendyol.com) | UAE (version /en/) | AED | Playwright (SPA React) |
| Daraz (daraz.pk) | Pakistan | PKR | Hybride (requests + Playwright) |

**101 produits** répartis sur **15 catégories** :

| Catégorie | Sous-catégorie | IDs |
|---|---|---|
| Electronique | Smartphones | 0–21 |
| Electronique | Casques audio & Écouteurs | 22–30 |
| Beauté & Cosmétiques | Parfums | 31–37 |
| Beauté & Cosmétiques | Produits cosmétiques | 38–47 |
| Mode & Sport | Chaussures | 48–49 |
| Electronique | Tablettes | 50–55 |
| Electronique | Powerbanks | 56 |
| Accessoires & Mode | Montres | 57–72 |
| Electronique | Télécommandes | 73–74 |
| Electronique | Chargeurs | 75–76 |
| Informatique | Souris | 77–83 |
| Informatique | Clés USB | 84–88 |
| Gaming & Jeux vidéo | Manettes de jeux | 89–94 |
| Sécurité & Maison connectée | Caméras surveillance Wi-Fi | 95–98 |
| Informatique | Webcams | 99–101 |

---

## Technologies utilisées et justifications

### Python 3.11+

Langage principal du projet. Choisi pour sa richesse en bibliothèques de scraping, son écosystème data science (utilisé dans les tâches aval), et sa lisibilité.

### requests + BeautifulSoup4 + lxml

- **requests** : bibliothèque HTTP standard pour les sites rendus côté serveur (Jumia). Permet le contrôle précis des headers, sessions et cookies.
- **BeautifulSoup4 + lxml** : parsing HTML rapide et robuste. Utilisé pour extraire les balises JSON-LD (`<script type="application/ld+json">`) et les sélecteurs CSS de fallback.
- **Justification :** Pour Jumia, le contenu est disponible dans le HTML initial — Playwright serait inutilement coûteux.

### Playwright (playwright-python)

- Automatisation d'un navigateur Chrome réel en mode persistant (headless=False, channel="chrome").
- Utilisé pour **Wildberries** et **Trendyol**, deux Single Page Applications (SPA) React dont tout le contenu est rendu dynamiquement par JavaScript, inaccessible avec requests seul.
- **Justification :** L'approche requests échoue sur ces sites car le HTML retourné par le serveur est un shell vide — le contenu visible (prix, titre, images) n'existe qu'après exécution du JavaScript côté client. Playwright exécute ce JavaScript exactement comme un utilisateur réel.
- Un **singleton** (`playwright_manager.py`) partage un unique navigateur entre Trendyol et Daraz pour éviter d'ouvrir plusieurs instances Chrome simultanément.

### Approche hybride pour Daraz

Daraz expose ses métadonnées (titre, images) via JSON-LD dans le HTML statique, mais le prix nécessite l'exécution JavaScript. Le scraper Daraz combine donc :
- **requests** pour le JSON-LD (rapide, sans navigateur)
- **Playwright** uniquement pour le prix (sélecteur CSS `pdp-price_type_normal`)

Cette approche réduit la charge sur Playwright et accélère le scraping.

### JSON-LD (Schema.org)

Format de données structurées embarqué dans les pages HTML de tous les sites cibles. Il fournit de manière fiable : titre, marque, prix, devise, images, dans un format standardisé. Utilisé en priorité ; les sélecteurs CSS servent uniquement de fallback.

### openpyxl

Lecture du fichier d'entrée `input/scp.xlsx` qui contient les URLs des produits par site et par identifiant. Choisi car le fichier source est au format Excel.

### ThreadPoolExecutor (concurrent.futures)
Utilisé dans `download_images.py` pour télécharger les images en parallèle (4 threads par défaut). Chaque image est indépendante — le parallélisme réduit le temps total de téléchargement de manière quasi-linéaire.
---
## Structure des fichiers
```
pfa_scraping/
│├── input/
│   └── scp.xlsx                    # Fichier source : URLs produits par site
│
├── output/
│   ├── produits.csv                # Résultat Tâche 1 (400 lignes, 14 colonnes)
│   └── images/                     # Résultat Tâche 2
│       ├── jumia/{id}/image_N.jpg
│       ├── wildberries/{id}/image_N.jpg
│       ├── trendyol/{id}/image_N.jpg
│       └── daraz/{id}/image_N.jpg
│
├── scrapers/
│   ├── __init__.py
│   ├── playwright_manager.py       # Singleton navigateur Chrome partagé
│   ├── jumia_scraper.py            # Scraper Jumia (requests + BS4)
│   ├── wildberries_scraper.py      # Scraper Wildberries (Playwright)
│   ├── trendyol_scraper.py         # Scraper Trendyol (Playwright + /en/)
│   └── daraz_scraper.py            # Scraper Daraz (hybride)
│
├── main.py                         # Orchestrateur Tâche 1 (scraping métadonnées)
├── download_images.py              # Tâche 2 : téléchargement images
├── utils.py                        # Fonctions partagées (session, JSON-LD, prix)
│
├── fill_categories.py              # Post-traitement : remplissage catégories CSV
├── impute_prix.py                  # Post-traitement : imputation prix manquants
├── sort_csv.py                     # Post-traitement : tri du CSV
│
├── check_images.py                 # Vérification : intégrité des URLs images
├── check_empty_prices.py           # Vérification : prix manquants
│
└── requirements.txt                # Dépendances Python
```

---

## Pipeline d'exécution

### Tâche 1 — Scraping des métadonnées

```bash
# 1. Installer les dépendances
pip install -r requirements.txt
playwright install chrome

# 2. Lancer le scraping
python main.py

# 3. Post-traitements
python fill_categories.py     # Remplir catégorie / sous_categorie
python impute_prix.py         # Imputer les prix manquants (produits OOS)
python sort_csv.py            # Trier le CSV par id puis par site
```

### Tâche 2 — Téléchargement des images

```bash
# Téléchargement complet (tous les sites)
python download_images.py --workers 6

# Options disponibles
python download_images.py --site jumia       # Un seul site
python download_images.py --id 5             # Un seul produit
python download_images.py --no-resume        # Re-télécharger même si déjà présent
```

---

## Points techniques notables

### Gestion des produits hors-stock (OOS)

Wildberries et Trendyol affichent certains produits sans prix (rupture de stock). Ces produits sont conservés avec `statut_scraping=ok` et un prix vide. Le script `impute_prix.py` estime ensuite le prix manquant par la **moyenne des prix des 3 autres sites**, convertis en USD comme devise pivot, puis reconvertis dans la devise locale.

### Sélecteur de pays Trendyol

Trendyol redirige les IPs hors-Turquie vers une page `/en/select-country`. La stratégie adoptée :
1. Forcer le préfixe `/en/` dans toutes les URLs Trendyol pour tenter l'accès direct
2. Si redirection détectée, sélectionner UAE via `page.evaluate()` (JavaScript direct, bypass overlay OneTrust + React event handling)

### Filtrage des images parasites

Les pages Trendyol embarquent des images tierces (bannières OneTrust/cookielaw, logos de certification ISO/PCI-DSS) qui seraient inutilisables pour la résolution d'entités visuelles. Un filtre par domaine (`EXCLUDED_DOMAINS`) les exclut systématiquement.

### Mécanisme de reprise (resume)

`main.py` charge en mémoire les lignes déjà scrapées avec `statut=ok` au démarrage. En cas d'interruption, relancer le script reprend là où il s'est arrêté sans écraser les données existantes. `download_images.py` implémente le même principe : les images déjà présentes sur disque sont ignorées.
