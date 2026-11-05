# Évaluation commune de l'imputation

## Organisation

Une seule base Parquet filtrée par région, filière solaire F5 et total des puissances P0. Lecture Arrow par lots et par colonnes : les 34 millions de lignes ne sont pas chargées en mémoire.

Pour la Bretagne : 52 608 observations, environ 1,3 Mo pour les trois colonnes source en pandas. Cette petite série peut rester en mémoire pendant les essais.

```text
data/imputed/production_regionale/region_53/
├── bases/<source_id>/
│   ├── observations.parquet
│   ├── natural_gaps.parquet
│   └── manifest.json
├── evaluations/<evaluation_id>/
│   ├── gaps.parquet
│   ├── masks.parquet
│   ├── truth.parquet
│   └── manifest.json
└── runs/<evaluation_id>/references/<run_id>/
    ├── predictions_linear.parquet
    ├── predictions_previous_day.parquet
    ├── predictions_seasonal_median.parquet
    ├── scores.parquet
    ├── scores_global.csv
    ├── scores_stratified.csv
    └── manifest.json
```

- `observations.parquet` : horodates UTC, énergie en Wh, comptage des sites et indicateurs de présence ; valeurs manquantes conservées.
- `natural_gaps.parquet` : durées et horaires des vrais trous, avec les éventuels manques simultanés des comptages.
- `gaps.parquet` : blocs artificiels, phases, dates, durées, modèles de trous utilisés et poids par durée.
- `masks.parquet` : créneaux à masquer, partagés entre toutes les méthodes.
- `truth.parquet` : observations cachées, réservées au calcul des erreurs.
- `manifest.json` : filtres, source, paramètres, graine, périodes et empreintes des fichiers.

Les résultats de chaque méthode seront enregistrés séparément dans `data/imputed`, comme des tables d'estimations par horodate. Ils référenceront la même base : aucune duplication des 34 millions de lignes. Une série complétée pourra être matérialisée à partir de la base et de ces estimations pour Q95/STL.

`data/raw` reste intact. Les dossiers d'expérience ne sont pas écrasés. Même source et mêmes paramètres : réutilisation après vérification des empreintes. Une autre graine crée d'autres masques, en réutilisant la base.

## Préparer les fichiers

```bash
.venv/bin/python scripts/module_2/prepare_imputation_evaluation.py --region 53
```

Par défaut : graine 42, 100 trous par phase, heure française. Le découpage des 36 mois bretons donne :

| Usage | Période locale |
| --- | --- |
| Contexte initial non masqué artificiellement | juillet 2023 à juin 2024 |
| Validation : méthodes et pondérations | juillet 2024 à juin 2025 |
| Calibration : intervalles de prédiction | juillet à décembre 2025 |
| Test final : évaluation après choix définitifs | janvier à juin 2026 |

Ce test final ne couvre pas toutes les saisons sur une année complète. Les comparaisons d'historique court/long utiliseront les mêmes blocs en limitant le contexte ; les premiers mois ne sont pas directement comparables à une année disposant de davantage d'historique.

Options : `--seed`, `--gaps-per-split`, `--timezone`, `--data-dir`, `--output-dir`, `--batch-size` et `--split-starts YYYY-MM YYYY-MM YYYY-MM`.

## Construction des masques

- Masquer uniquement des blocs dont les productions sont réellement connues, avec un voisin connu de chaque côté.
- Reprendre les durées des trous naturels ; conserver leur heure locale de début et préférer la même saison. Un changement de saison faute de candidat est indiqué dans `season_matched`.
- Inclure chaque durée au moins une fois par phase lorsque le budget le permet, puis échantillonner les modèles de trous naturels. Les durées rares sont donc surreprésentées : `duration_weight` permet de pondérer les futurs scores agrégés par leur fréquence naturelle.
- Garder les blocs et leurs voisins sans chevauchement. Les vrais manques restent manquants.
- Reproduire les manques simultanés des comptages seulement lorsqu'ils existent dans le trou naturel utilisé comme modèle. En Bretagne, les comptages sont connus même quand l'énergie manque : ils restent disponibles dans les blocs artificiels correspondants.

La préparation ne remplit aucune valeur et n'entraîne aucun modèle. Les méthodes devront prédire des blocs entiers sans révéler les vérités intermédiaires pendant leur reconstruction.

## Charger les entrées et mesurer les erreurs

```python
from enedis.prediction.imputation_evaluation import load_evaluation_split, score_reconstruction

inputs, truth, gaps = load_evaluation_split(evaluation_dir, "validation")
# predictions : Series des estimations en Wh, indexée par horodate avec fuseau.
scores = score_reconstruction(truth, predictions, weight_column="duration_weight")
```

`inputs` masque toutes les cibles artificielles avant calcul des features et s'arrête à la fin de la phase demandée. Les observations de calibration/test ne sont donc pas accessibles pendant les phases précédentes. Ne pas utiliser directement la base non masquée ni les colonnes de vérité comme contexte du modèle.

Pour la marche avant, limiter encore les observations au début de chaque trou. Pour la marche arrière, des observations ultérieures au trou sont autorisées uniquement avant `reconstruction_as_of`, fin exclue de la phase. Ce protocole concerne la reconstruction rétrospective ; une validation de prévision future devra refaire l'imputation avec les seules données disponibles à son émission.

`reconstruct_with_model` réalise le premier essai avec modèle : validation uniquement, marche avant, groupes A+B+C. Il retourne les prédictions en Wh et les diagnostics par trou. Voir [l'exemple d'appel](models.md#premier-essai-de-remplissage--validation-marche-avant-abc).

`score_reconstruction` calcule couverture des prédictions, MAE, RMSE et biais en MWh sur les seules observations cachées connues. Comparer aussi les erreurs sur les mêmes points lorsque les méthodes ne remplissent pas tous les trous. Les futurs rapports sépareront les durées, saisons et périodes diurnes/nocturnes ; la classification solaire demandera un point régional explicite.

`weight_column="duration_weight"` pondère les erreurs agrégées selon les durées naturelles ; sans cet argument, les erreurs sont des moyennes non pondérées. La couverture en nombre de points reste indiquée, avec une couverture pondérée séparée. Conserver aussi les scores détaillés par durée. Les intervalles seront calibrés sur la phase dédiée puis évalués sur le test final ; les répétitions ne constituent pas à elles seules une mesure d'incertitude calibrée.

## Références simples

```bash
.venv/bin/python scripts/module_2/run_imputation_references.py --region 53 --latitude 48 --longitude -3
```

La commande retrouve l'expérience de préparation par défaut, puis traite uniquement la validation. Les coordonnées ci-dessus sont un point régional provisoire : elles servent à classer jour/nuit selon l'élévation solaire à l'horodate, sans modifier les estimations. Sans coordonnées, les scores globaux, par heure, saison et durée restent disponibles.

| Méthode | Calcul | Informations autorisées |
| --- | --- | --- |
| `linear` | Interpolation en temps UTC entre les deux créneaux connus encadrant le bloc | Deux côtés du trou, à l'intérieur de la phase ; aucune extrapolation si un bord manque |
| `previous_day` | Valeur du jour précédent à la même heure locale | Observations strictement antérieures au début du bloc ; aucune valeur de remplacement si J−1 manque |
| `seasonal_median` | Médiane à la même heure sur les 7 jours précédents, avec au moins 3 valeurs connues | Même passé strict ; les valeurs absentes sont ignorées, les zéros conservés |

Les trois méthodes travaillent sur des entrées masquées identiques. Aucune estimation n'est réinjectée comme observation dans un autre créneau ou une autre méthode. En heure locale, une heure historique ambiguë ou inexistante au changement d'heure donne une référence manquante.

Options : `--evaluation-dir` pour une expérience précise, `--methods`, `--days`, `--min-observations`, `--day-basis local|utc`, `--latitude` et `--longitude`. Avec `--evaluation-dir`, les paramètres de préparation ne servent pas à recréer les masques. `--split` est fixé à `validation` par défaut ; calibration et test doivent être demandés explicitement lorsque les choix sont arrêtés.

Les prédictions sont des tables légères par méthode, avec horodate, estimation en Wh, identifiant du trou, nombre de références disponibles et coupure d'information. Elles ne contiennent pas la vérité. La base et les fichiers de préparation restent inchangés ; une exécution identique réutilise les résultats vérifiés.

### Résultats sur la validation bretonne

100 trous, 204 valeurs cachées. Les trois méthodes reconstruisent **195 points en commun**, dont **114 diurnes** selon le point provisoire 48° N, 3° O. Erreurs ci-dessous pondérées selon la fréquence naturelle des durées, en MWh par créneau de 30 minutes.

| Méthode | Couverture sur les 204 points | MAE sur les 195 communs | RMSE sur les 195 communs | MAE sur les 114 diurnes communs |
| --- | ---: | ---: | ---: | ---: |
| Interpolation linéaire | 100 % | 4,490 | 15,194 | 8,869 |
| J−1 | 95,6 % | 8,295 | 20,784 | 17,470 |
| Médiane des 7 jours | 100 % | 8,625 | 19,415 | 18,125 |

- L'interpolation est la meilleure référence globale sur ces blocs fermés, avec un bord droit connu. Ce résultat ne constitue pas une performance de prévision utilisant seulement le passé.
- Parmi les références sur le passé, J−1 obtient la plus faible MAE et la médiane la plus faible RMSE sur les mêmes points. Les deux restent utiles pour comparer les modèles suivants.
- J−1 laisse 9 points sans estimation faute de référence disponible. Les tableaux distinguent les scores sur tous les points disponibles et les scores sur l'intersection commune.
- Les scores nocturnes et par durée sont conservés dans `scores_stratified.csv` ; le classement global ne garantit pas la même hiérarchie pour chaque type de trou.
- Sur les points communs des deux trous de 9 h 30 de cette validation, la MAE atteint 83,262 MWh pour l'interpolation, contre 25,468 pour J−1. Ces cas soulignent la limite de l'interpolation sur un long bloc ; davantage d'exemples seront nécessaires avant d'en tirer une règle de sélection par durée.

Calibration, test final et vrais trous ne sont pas reconstruits par ce lancement. Ces résultats fixent les références à dépasser avant de retenir un modèle ou de compléter l'historique final.

## Premier test Kumo

Depuis la racine, petit essai forward A+B+C sur les trois premiers trous de validation :

```bash
.venv/bin/python scripts/module_2/impute_data.py \
  --latitude 48.170199 --longitude -2.956569 \
  --size small --num-estimators 1 --max-gaps 3
```

Le point breton est indicatif et doit rester identique pour les features et les scores jour/nuit. Les poids sont téléchargés au premier fit si nécessaire ; le calcul est local. Pour évaluer tous les trous avec ce même paramétrage, retirer `--max-gaps 3`.

Sans `--evaluation-dir`, le script prépare ou retrouve l'expérience avec région 53, graine 42 et 100 trous par phase. Pour réutiliser une expérience précise, fournir son chemin avec `--evaluation-dir`. Seule sa validation est évaluée, toujours en marche avant, avec les 15 features A+B+C. Les prédictions sont bornées à zéro avant le calcul des scores.

Pour comparer A+B avec le même clipping, ajouter `--groups A B`. Les masques restent identiques.

Options principales : `--context-size` (2048), `--min-observations` (2), `--size` (`large` par défaut), `--num-estimators` (8), `--batch-size` (256), `--device` (`auto`) et `--model-seed` (42). `--model-seed` change Kumo sans changer les masques. `--seed` concerne uniquement la préparation de l'expérience.

`--max-gaps` limite les cibles évaluées aux premiers trous chronologiques. Tous les autres masques restent appliqués ; leurs vérités ne redeviennent pas disponibles au modèle. Les scores d'un essai limité sont exploratoires ; les pondérations de l'expérience d'origine sont conservées.

Le terminal affiche l'avancement et les scores globaux/jour/nuit : couverture, MAE, RMSE et biais pondérés, en MWh par demi-heure. Les prédictions restent en Wh.

Résultats dans `runs/<evaluation_id>/kumo_forward_abc/<run_id>/` (ou `kumo_forward_ab` avec `--groups A B`) :

- `predictions.parquet` : estimations aux seules horodates masquées évaluées, sans vérité. `prediction_wh` contient les valeurs clippées utilisées pour les scores ; `prediction_raw_wh` conserve les sorties brutes.
- `diagnostics.parquet` : tailles du contexte, statuts, nombres de prédictions clippées et durées par trou.
- `scores.parquet`, `scores_global.csv`, `scores_stratified.csv` : résultats pondérés et non pondérés, par durée, heure, saison et jour/nuit.
- `manifest.json` : expérience, paramètres Kumo, coordonnées, identifiants des trous, versions des dépendances et empreintes du code et des sorties.

Même expérience, mêmes paramètres et même code : résultat existant vérifié et relu, sans nouveau fit ni écrasement. Les vrais trous restent manquants ; aucune série entièrement remplie n'est produite ici.

Ces scores décrivent Kumo seul. Pour le comparer aux références, recalculer les scores sur les horodates prédites communes aux méthodes comparées.

Les lags à J−1, J−2, J−7 et J−365 sont calculés sur la série masquée, en jours UTC de 24 heures. Un lag dans un trou ou avant le début de l'historique reste NaN. Les anciens résultats A+B sans clipping sont conservés dans leur dossier.
