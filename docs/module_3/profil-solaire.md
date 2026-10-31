# Profil solaire régional

Script : `scripts/module3/profil_solaire_regions.py`. Exploration préalable : `scripts/module3/explore_production.py`.

## Données

`data/raw/production_regionale/` : Parquet partitionné par année, pas de 30 minutes.

- Filtres : `filiere_de_production == "F5 : Solaire"` et `plage_de_puissance_injection == "P0 : Total toutes puissances"`. Les catégories `F0` et `P0` sont déjà des totaux : il faut filtrer sur les deux colonnes pour ne pas compter plusieurs fois la même énergie.
- Valeur utilisée : `total_energie_injectee_wh` (en Wh), convertie en MWh.
- `horodate` est en UTC : conversion vers `Europe/Paris` avant de calculer l'heure du jour.
- `metadata.json` est dans le même dossier et fait échouer `pyarrow` : utiliser `exclude_invalid_files=True`.

## Contrôles (année 2025)

- 12 régions dans les données.
- 210 240 lignes, soit 12 × 17 520 demi-heures : aucun trou.
- 0 doublon sur (région, horodate).

## Résultats

Toutes les courbes sont en cloche centrée sur midi, sans décalage ni anomalie : fuseau horaire et filtres validés. L'été est plus haut et plus long que l'hiver.

Pic moyen d'été 2025, en MWh par demi-heure :

| Région | Pic d'été 2025 |
|---|---|
| Nouvelle-Aquitaine | 1271 |
| Occitanie | 1212 |
| Auvergne-Rhône-Alpes | 847 |
| Provence-Alpes-Côte d'Azur | 704 |
| Pays de la Loire | 498 |
| Grand-Est | 421 |
| Centre-Val de Loire | 378 |
| Bourgogne-Franche-Comté | 341 |
| Bretagne | 205 |
| Hauts-de-France | 182 |
| Normandie | 114 |
| Île-de-France | 92 |

- La Nouvelle-Aquitaine injecte environ treize fois plus que l'Île-de-France : une pression moyenne nationale n'aurait pas de sens, d'où l'approche par région.
- Pour PACA, le pic d'été passe d'environ 660 (moyenne 2023-2026) à 704 en 2025, ce qui correspond à la croissance du parc.

## Limites

- Il s'agit de l'énergie injectée sur le réseau, sans l'autoconsommation.
- Les valeurs sont absolues et dépendent de la taille du parc de chaque région. Pour comparer l'ensoleillement, il faudrait les ramener à la puissance installée (fichier photovoltaïque régional).
- Le contrôle des doublons a été fait sur 2025. Les autres années n'ont pas été vérifiées.
