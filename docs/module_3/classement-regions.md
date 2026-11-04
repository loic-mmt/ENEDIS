# Classement des régions : creux de midi et rampe du soir

Code : `src/enedis/scenarios/charge_nette.py` (fonctions), `scripts/module3/classement_regions.py` (calcul sur les 12 régions et graphique), `tests/test_scenarios_charge_nette.py` (10 tests unitaires).

## Objectif

Étendre à toutes les régions le calcul de la charge nette (voir `charge-nette.md`) et en tirer deux indicateurs de pression potentielle, pour une saison estivale et une saison hivernale types.

## Méthode

Pour chaque région et chaque période (été 2024 : juin à août ; hiver 2023-24 : décembre à février) :

1. Consommation résidentielle régionale estimée, par demi-heure : forme du profil moyen d'un client (`RES2-6-9`), calée sur la consommation annuelle résidentielle 2024 de la région.
2. Production solaire injectée moyenne par demi-heure (`F5`, `P0`), en heure française.
3. Charge nette = consommation moins solaire.
4. Indicateurs :
   - **creux de midi** : minimum de la charge nette, et heure où il est atteint ;
   - **rampe du soir** : plus forte hausse de la charge nette sur une heure, pour un départ entre 16 h et 23 h.
5. Versions **relatives** : chaque indicateur divisé par la consommation moyenne de la région. C'est la version à utiliser pour comparer les régions, car en valeurs absolues les grandes régions écrasent les petites.

Les valeurs absolues sont en MWh par demi-heure.

## Résultats

### Été 2024 (classé par creux relatif)

| Région | Creux (MWh) | Heure du creux | Rampe (MWh) | Heure de la rampe | Creux relatif | Rampe relative |
| --- | --- | --- | --- | --- | --- | --- |
| Nouvelle-Aquitaine | -528,72 | 16 h | 367,09 | 18 h | -1,00 | 0,70 |
| Occitanie | -518,10 | 14 h 30 | 356,91 | 18 h | -0,97 | 0,67 |
| Centre-Val de Loire | -64,22 | 16 h 30 | 111,47 | 18 h | -0,28 | 0,49 |
| Provence-Alpes-Côte d'Azur | -123,25 | 11 h | 244,52 | 18 h | -0,25 | 0,50 |
| Pays de la Loire | -27,13 | 16 h 30 | 140,90 | 18 h | -0,08 | 0,41 |
| Bourgogne-Franche-Comté | -11,24 | 11 h | 98,39 | 18 h | -0,05 | 0,42 |
| Auvergne-Rhône-Alpes | -22,57 | 16 h 30 | 271,59 | 18 h | -0,03 | 0,42 |
| Grand-Est | 11,25 | 11 h | 127,67 | 18 h | 0,03 | 0,39 |
| Bretagne | 107,00 | 16 h 30 | 88,71 | 18 h | 0,35 | 0,29 |
| Hauts-de-France | 205,71 | 16 h 30 | 108,05 | 21 h 30 | 0,50 | 0,26 |
| Normandie | 153,27 | 16 h 30 | 78,84 | 21 h 30 | 0,51 | 0,26 |
| Île-de-France | 483,78 | 8 h 30 | 197,65 | 21 h 30 | 0,64 | 0,26 |

### Hiver 2023-24

- La charge nette ne devient négative dans aucune région : creux relatif entre 0,44 (Occitanie) et 0,81 (Île-de-France).
- Les rampes relatives sont presque identiques partout (0,16 à 0,20) : l'hiver ne différencie pas les régions.

## Lecture

- **Sept régions** passent en charge nette négative en été (excédent de solaire par rapport à la consommation estimée). La Nouvelle-Aquitaine et l'Occitanie sont nettement devant ; Grand-Est est quasi à zéro ; les régions du Nord restent nettement positives.
- La rampe du soir est la plus forte en Nouvelle-Aquitaine (0,70) et en Occitanie (0,67), puis en PACA (0,50) et Centre-Val de Loire (0,49).
- **Normaliser change le classement** : Auvergne-Rhône-Alpes est 3e en solaire brut (pic d'été 847 MWh par demi-heure) mais seulement 7e sur le creux relatif, car sa consommation est élevée.
- L'heure du creux n'est pas toujours à midi (16 h en Nouvelle-Aquitaine, 14 h 30 en Occitanie) : la consommation résidentielle estimée baisse en fin d'après-midi alors que le solaire reste élevé.
- Pour les régions du Nord, l'heure du creux (8 h 30, 16 h 30) et celle de la rampe (21 h 30) viennent de la forme de la consommation seule, pas du solaire. Le creux n'a de sens que là où il est négatif ou proche de zéro.

## Limites

- **Résultat indicatif.** La consommation est résidentielle et estimée à partir de 500 clients, le solaire injecté est total (grandes centrales comprises). L'excédent de midi est exagéré, surtout en Nouvelle-Aquitaine et en Occitanie.
- Hypothèse d'un profil de consommation unique pour toutes les régions (celui des 500 clients).
- Moyennes sur trois mois : les journées extrêmes sont lissées.
- Unité de `valeur` non confirmée (sans effet sur ces indicateurs).
- Une partie du solaire est reconstituée par profilage plutôt que mesurée (remarque de l'équipe sur les données de production) : les très faibles valeurs nocturnes peuvent en venir. Effet attendu faible sur ces indicateurs, mais non mesuré.

## Suite

1. Refaire le calcul avec les petites puissances solaires seulement (plages `P1` à `P3`, plus proches du résidentiel) et vérifier que le classement tient.
2. Brancher la consommation totale de la région à la place du résidentiel.
3. Mesurer la production nocturne (maximum entre 22 h et 4 h) pour confirmer que l'effet du profilage est négligeable.
4. Appliquer les scénarios 2030 au profil de charge nette.
