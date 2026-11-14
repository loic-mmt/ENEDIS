# Parc solaire par classe de puissance

Script : `scripts/module3/parc_par_puissance.py`. Données : `data/raw/production_regionale/` (filière `F5 : Solaire`), colonne `nb_points_injection`.

## Objectif

Les valeurs d'énergie des plages de puissance `P1` à `P7` sont vides dans une partie des lignes (voir `classement-regions.md`). Le nombre de points de raccordement (`nb_points_injection`) est en revanche renseigné pour toutes les plages. Il donne le parc d'installations par classe de puissance et son évolution, utile pour construire les scénarios solaire.

Classes : petites puissances `P1` à `P3` (jusqu'à 100 kW), grandes puissances `P4` à `P7`.

## Contrôles

- Période : du 01/07/2023 au 30/06/2026.
- Aucune valeur absente dans `nb_points_injection`.
- Le nombre de points est stable au cours de la journée (Occitanie, `P0` : de 178 652 à 178 684 selon l'heure). Le script retient le maximum de chaque jour puis la médiane du mois.
- La somme des plages `P1` à `P7` égale `P0` en fin de période (rapport de 1,000 dans 11 régions, 0,999 en Centre-Val de Loire).

## Résultats

Nombre de points de raccordement, juillet 2023 et juin 2026 :

| Région | Total 2023-07 | Total 2026-06 | Croissance | Petites 2026-06 | Grandes 2023-07 | Grandes 2026-06 | Part des petites |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Occitanie | 118 915 | 214 910 | +80,7 % | 207 714 | 2 816 | 7 144 | 96,7 % |
| Auvergne-Rhône-Alpes | 119 743 | 212 070 | +77,1 % | 205 897 | 1 414 | 6 111 | 97,1 % |
| Nouvelle-Aquitaine | 92 836 | 173 831 | +87,2 % | 166 511 | 2 175 | 7 255 | 95,8 % |
| Provence-Alpes-Côte d'Azur | 65 777 | 109 726 | +66,8 % | 107 191 | 1 370 | 2 522 | 97,7 % |
| Pays de la Loire | 62 264 | 101 256 | +62,6 % | 96 609 | 911 | 4 626 | 95,4 % |
| Grand-Est | 43 049 | 75 487 | +75,4 % | 72 133 | 858 | 3 336 | 95,6 % |
| Bourgogne-Franche-Comté | 36 233 | 63 870 | +76,3 % | 61 585 | 319 | 2 260 | 96,4 % |
| Bretagne | 31 536 | 56 655 | +79,7 % | 54 364 | 406 | 2 272 | 96,0 % |
| Hauts-de-France | 33 036 | 56 038 | +69,6 % | 54 474 | 269 | 1 558 | 97,2 % |
| Centre-Val de Loire | 22 704 | 40 351 | +77,7 % | 37 841 | 457 | 2 489 | 93,8 % |
| Normandie | 21 759 | 38 220 | +75,7 % | 36 945 | 208 | 1 273 | 96,7 % |
| Île-de-France | 23 393 | 36 047 | +54,1 % | 35 510 | 120 | 531 | 98,5 % |

(Valeurs arrondies à l'unité ; certaines médianes mensuelles tombent sur des demi-points.)

## Lecture

- Le parc a augmenté de 54 % (Île-de-France) à 87 % (Nouvelle-Aquitaine) en trois ans. Les petites installations représentent 94 % à 98,5 % des points de raccordement.
- Les grandes puissances partent d'un petit nombre de points, donc leurs croissances en pourcentage sont très élevées (de +84 % à +609 %). En valeur absolue, c'est la Nouvelle-Aquitaine (environ +5 100 points), Auvergne-Rhône-Alpes (+4 700), l'Occitanie (+4 300) et les Pays de la Loire (+3 700) qui gagnent le plus de grandes installations.
- Sur le graphique, la croissance des petites puissances paraît régulière et un peu plus lente en 2026, celle des grandes puissances semble s'accélérer depuis 2025 dans plusieurs régions (lecture visuelle, non quantifiée).

## Limites

- Un nombre de points de raccordement n'est ni une puissance installée ni une énergie : une installation de la classe `P7` pèse beaucoup plus qu'une de la classe `P1`.
- Trois ans d'historique seulement : une extrapolation à 2030 repose sur des hypothèses.
- Le lien entre nombre de points et énergie par classe n'est pas établi, puisque l'énergie des plages détaillées est incomplète.

## Suite

Utiliser ces croissances, par classe et par région, comme base des scénarios solaire (bas, central, haut), et les relier à la puissance installée du fichier `puissance_photovoltaique/puissance-solaire-installee-region.csv`, pas encore exploité.