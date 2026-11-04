# Courbes de charge résidentielles

Script : `scripts/module3/profil_conso.py`. Exploration préalable : `scripts/module3/explore_courbes_charge.py`.

## Données

`data/raw/courbes_de_charge/RES2-6-9.csv` : séparateur `;`, colonnes `ID`, `horodate` (avec décalage horaire), `valeur`, pas de 30 minutes. Les deux fichiers ont été exploités et comparés (voir `classement-regions.md`).

## Contrôles

| Indicateur | Valeur |
|---|---|
| Lignes | 8 736 000 |
| Identifiants | 500 |
| Doublons (ID, horodate) | 0 |
| Valeurs manquantes | 0 |
| Moyenne de `valeur` | 663,6 |
| Médiane | 325,1 |
| Maximum | 8 998 |

500 clients × 17 472 demi-heures (364 jours) = 8 736 000 : la série est complète, du 01/11/2023 au 29/10/2024.

## Contrôles (`RES2-9-12`)

| Indicateur | Valeur |
| --- | --- |
| Lignes | 8 736 000 |
| Identifiants | 500 |
| Doublons (ID, horodate) | 0 |
| Valeurs manquantes | 0 |
| Moyenne de `valeur` | 926,2 |
| Médiane | 512,3 |
| Maximum | 12 000 |

Même période que `RES2-6-9` (du 01/11/2023 au 29/10/2024). Les deux fichiers n'ont **aucun identifiant en commun** : on dispose de 1 000 foyers distincts.

## Unité non confirmée

Les maxima (8 998 pour `RES2-6-9`, 12 000 pour `RES2-9-12`) sont compatibles avec une puissance moyenne en watts pour des abonnements de 6 à 9 kVA et de 9 à 12 kVA, mais ce n'est qu'une supposition. À vérifier sur la description du jeu de données d'Enedis. La signification de `6-9` et `9-12` (tranche de puissance souscrite) n'est pas vérifiée non plus.

## Résultats

- L'hiver consomme environ deux fois plus que l'été (de l'ordre de 800 à 1 200 contre 300 à 650), ce qui est cohérent avec le chauffage électrique.
- Pic du soir vers 19 h en hiver, valeurs qui restent élevées la nuit.
- En été : creux le matin, petite bosse vers 12 h 30 - 13 h, creux vers 16 h 30, puis montée jusqu'à 22 h 30.

Le décalage de la problématique apparaît déjà : le solaire est maximal à 12 h 30, quand la consommation résidentielle est basse, et nul à 19-23 h quand elle est maximale.

## Limites

- 500 clients ne représentent pas une région (voir `charge-nette.md` pour l'extrapolation).
- La période (11/2023 à 10/2024) ne coïncide pas avec le profil solaire de référence (2025) : on compare des journées types.