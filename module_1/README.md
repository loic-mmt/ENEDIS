# Module 1 — Comprendre et préparer les données

Ce dossier regroupe le plan, les décisions et les scripts de traitement du module 1. La description générale des données et leur inventaire restent dans le dossier commun `docs/`. Le but est de préparer la future base PostgreSQL/PostGIS pour les autres membres du projet.

## Où trouver quoi ?

```text
module_1/
├── README.md                    ← commencer ici
├── docs/
│   ├── decisions-traitement.md   ← résultats expliqués et décisions
│   └── plan-module-1.md          ← plan complet jusqu’à la base SQL
└── scripts/
    ├── profile_data.py          ← compter et analyser les valeurs manquantes
    └── check_consommation.py    ← vérifier les formats et les doublons
```

Les fichiers reçus restent dans `data/raw/`, à la racine du projet. Les rapports générés restent dans `data/processed/rapports/`. Les scripts ne modifient pas les données brutes.

## Dans quel ordre lire les documents ?

1. [Description des données](../docs/data.md) : ce que contient chaque fichier et à quoi il peut servir.
2. [Inventaire et contrôles](../docs/controle-donnees.md) : volumes, périodes et problèmes connus.
3. [Résultats et décisions](docs/decisions-traitement.md) : ce qu’on a trouvé dans la consommation et ce qu’on va en faire.
4. [Plan du module 1](docs/plan-module-1.md) : organisation du travail et proposition de base SQL.

## Comment lancer les traitements ?

Exécuter les commandes **depuis la racine de `Projet_Tuteuré`**, là où se trouvent `.venv/`, `data/` et `module_1/`.

### Étape 1 — Analyser les cellules vides de consommation

```bash
.venv/bin/python module_1/scripts/profile_data.py
```

Ce script produit quatre rapports dans `data/processed/rapports/` :

| Rapport | Contenu |
| --- | --- |
| `consommation_valeurs_manquantes.csv` | Cellules vides par colonne |
| `consommation_manques_par_annee.csv` | Cellules vides par année et colonne |
| `consommation_manques_par_categorie_secteur.csv` | Cellules vides par catégorie, secteur et colonne |
| `consommation_combinaisons_manques.csv` | Informations qui manquent ensemble et indicateur de secretisation |

### Étape 2 — Vérifier les formats et les doublons

```bash
.venv/bin/python module_1/scripts/check_consommation.py
```

Ce script produit `consommation_verification_formats_et_doublons.csv`, dans le même dossier de rapports. Il contrôle les années, les formats des codes commune, les consommations renseignées, le nombre de sites et les répétitions dans tout le fichier.

Ces deux commandes recalculent leurs rapports et remplacent les anciens rapports du même nom. Elles ne remplissent pas les valeurs manquantes et ne suppriment aucune observation.

## Où en est-on ?

- La consommation a été analysée pour les valeurs manquantes, les formats et les doublons.
- Les décisions actuelles sont décrites dans [decisions-traitement.md](docs/decisions-traitement.md).
- Les autres jeux sont décrits et restent tous dans le périmètre du module ; ces deux scripts ne les contrôlent pas encore.
- La vérification des définitions officielles, les diagnostics des autres sources, l’harmonisation géographique et la création de la base restent à faire.

La [problématique générale](../docs/problematique.md) et le [plan du module 2](../docs/plan-module-2.md) restent dans le dossier commun `docs/`. Les scripts de téléchargement et de conversion restent dans le dossier commun `scripts/`.
