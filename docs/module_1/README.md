# Module 1 — Comprendre et préparer les données

Ce dossier regroupe le plan et les décisions du module 1. Les scripts de traitement se trouvent dans `scripts/module_1/`, à la racine du projet. La description générale des données et leur inventaire restent dans le dossier commun `docs/data/`. Le but est de préparer la future base PostgreSQL/PostGIS pour les autres membres du projet.

## Où trouver quoi ?

```text
docs/module_1/
├── README.md                    ← commencer ici
├── decisions-traitement.md      ← résultats expliqués et décisions
└── plan-module-1.md             ← plan complet jusqu’à la base SQL

scripts/module_1/
├── profile_data.py              ← compter et analyser les valeurs manquantes
└── check_consommation.py        ← vérifier les formats et les doublons
```

Les fichiers reçus restent dans `data/raw/`, à la racine du projet. Les rapports générés restent dans `data/processed/rapports/`. Les scripts ne modifient pas les données brutes.

## Dans quel ordre lire les documents ?

1. [Description des données](../data/data.md) : ce que contient chaque fichier et à quoi il peut servir.
2. [Inventaire et contrôles](../data/controle-donnees.md) : volumes, périodes et problèmes connus.
3. [Résultats et décisions](decisions-traitement.md) : ce qu’on a trouvé dans la consommation et ce qu’on va en faire.
4. [Plan du module 1](plan-module-1.md) : organisation du travail et proposition de base SQL.

## Comment lancer les traitements ?

Exécuter les commandes **depuis la racine de `Projet_Tuteuré`**, là où se trouvent `.venv/`, `data/`, `docs/` et `scripts/`.

### Étape 1 — Analyser les cellules vides de consommation

```bash
.venv/bin/python scripts/module_1/profile_data.py
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
.venv/bin/python scripts/module_1/check_consommation.py
```

Ce script produit `consommation_verification_formats_et_doublons.csv`, dans le même dossier de rapports. Il contrôle les années, les formats des codes commune, les consommations renseignées, le nombre de sites et les répétitions dans tout le fichier.

Ces deux commandes recalculent leurs rapports et remplacent les anciens rapports du même nom. Elles ne remplissent pas les valeurs manquantes et ne suppriment aucune observation.

## Où en est-on ?

- La consommation a été analysée pour les valeurs manquantes, les formats et les doublons.
- Les décisions actuelles sont décrites dans [decisions-traitement.md](decisions-traitement.md).
- Les autres jeux sont décrits et restent tous dans le périmètre du module ; ces deux scripts ne les contrôlent pas encore.
- La vérification des définitions officielles, les diagnostics des autres sources, l’harmonisation géographique et la création de la base restent à faire.

La [problématique générale](../problematique.md) reste dans `docs/` et le [plan du module 2](../module_2/plan-module-2.md) dans `docs/module_2/`. Les scripts de téléchargement et de conversion restent dans le dossier commun `scripts/`.

## Préparer la base PostgreSQL/PostGIS

Les fichiers de création sont disponibles, **sans avoir été exécutés** :

- [Installation et ordre des commandes](installation-base.md).
- [Schéma et description des tables](schema-base.md).
- [SQL de création](../../sql/module_1/001_structure_base.sql).
- [Script d’import de consommation](../../scripts/module_1/import_consommation.py).

Le premier import conserve les données d’origine, crée une version typée de la consommation et garde les absences en `NULL`. Les imports des autres jeux restent à développer.

Pour savoir où ira chaque fichier reçu et pourquoi : [correspondance entre fichiers et tables](correspondance-fichiers-tables.md).
