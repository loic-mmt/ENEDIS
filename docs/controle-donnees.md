# Contrôle des données

## Fichiers présents

Tous les jeux sont dans `data/raw/`. `data/processed/` ne contient encore aucun jeu traité.

| Dossier | Fichiers | Lignes | Période |
| --- | --- | ---: | --- |
| `consommation/` | 1 CSV de consommation communale | 3 763 258 | 2011–2025 |
| `puissance_photovoltaique/` | CSV commune, département, EPCI, région + dictionnaire | 384 715 / 2 969 / 24 904 / 926 | 1900–2025 ; dates anciennes à vérifier |
| `bornes_recharge/` | CSV statique, dynamique, rapport de consolidation | 171 810 / 125 339 / 1 871 | Instantanés ; historique non vérifié |
| `reseau/` | `poste-electrique.csv` | 976 678 | Non daté dans le fichier |
| `reseau/` | `donnees-relatives-aux-lignes-et-aux-postes.csv` | 1 605 | 2011–2025 |
| `courbes_de_charge/` | `RES2-6-9.csv`, `RES2-9-12.csv` | 8 736 000 chacun | 01/11/2023–29/10/2024 |
| `production_regionale/` | 70 Parquet, partitions `year=2023` à `year=2026` | 34 089 984 | 01/07/2023–30/06/2026, heure française |

Production régionale : **1,28 Go**, avec `metadata.json`, `_conversion.json` et `_schema.txt`. PVGIS absent car problème d'API.

## Contrôles effectués

- **CSV :** lecture intégrale, UTF-8 et nombre de colonnes conformes ; clés de consommation et de puissance solaire uniques selon les dimensions contrôlées.
- **Parquet :** relecture intégrale, total de lignes et schémas vérifiés ; partitions annuelles contrôlées en `Europe/Paris`, timestamps stockés en UTC.
- Conversion de format uniquement : nettoyage métier à effectuer dans les pipelines d’ingestion database.

## À traiter à l’ingestion

- **Consommation :** 446 907 consommations totales manquantes ; distinguer absence et confidentialité, sans remplacement automatique par zéro.
- **Solaire :** expliquer les dates anciennes ; distinguer photovoltaïque, thermodynamique et types non renseignés. Puissances en MW.
- **IRVE statique :** 27 084 coordonnées signalées incorrectes ; 2 répétitions d’identifiant ne différant que par la ressource source.
- **IRVE dynamique :** 10 446 répétitions d’identifiant ; vérifier la clé temporelle avant jointure. Le rapport de consolidation reste une table de suivi.
- **Postes :** 15 codes commune absents ; vérifier géométries et systèmes de coordonnées. Les statistiques de réseau sont des agrégats, pas des tracés de lignes.
- **Courbes de charge :** vérifier unité, pas temporel, trous et doublons ID/horodatage ; 500 identifiants par fichier.
- **Production régionale :** vérifier les doublons entre pages d’origine ; éviter de sommer les catégories totales `P0`/`F0` avec leurs détails. Énergies en Wh.

Emplacements détaillés : [arbo.txt](../arbo.txt). Validation Parquet : [rapport](../data/raw/production_regionale/_conversion.json).
