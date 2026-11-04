# Feature Engineering — Production photovoltaïque

## 1. Objectif

L'objectif est de tester différentes combinaisons de features afin d'identifier celles qui améliorent le plus la prédiction de la production photovoltaïque.

Les features seront réparties en **6 groupes**, puis évaluées à l'aide d'un modèle de référence et du coefficient de détermination $(R^2)$.

## 2. Features à tester

### Groupe A — Calendrier

Ces variables permettent de capturer les cycles journaliers et saisonniers.

| Feature | Calcul / Librairie |
|---|---|
| `hour_sin`, `hour_cos` | Encodage cyclique de l'heure |
| `doy_sin`, `doy_cos` | Encodage cyclique du jour de l'année |
| `month` | `pandas.dt.month` |
| `week_of_year` | `pandas.dt.isocalendar().week` |
| `season` | Saison déduite du mois |
| `day_of_week` | `pandas.dt.dayofweek` |

Pour les variables cycliques :

$$
x_{\sin}=\sin\left(\frac{2\pi x}{T}\right)
$$

$$
x_{\cos}=\cos\left(\frac{2\pi x}{T}\right)
$$

Avec $(T=24)$ pour l'heure et $(T\approx365{,}2425)$ pour le jour de l'année.

### Groupe B — Astronomie

Ces variables décrivent le potentiel solaire théorique indépendamment des conditions météorologiques.

| Feature | Calcul / Librairie |
|---|---|
| `solar_elevation` | `pvlib.solarposition` |
| `solar_azimuth` | `pvlib.solarposition` |
| `daylight_duration` | `pvlib.solarposition.sun_rise_set_transit_spa` |

Ces calculs nécessitent les coordonnées géographiques d'un point représentatif de la région ainsi que les dates des observations.

### Groupe C — Lags

Ces variables représentent l'historique de production à différents horizons.

| Feature | Calcul |
|---|---|
| `lag_1d` | Production à J−1 |
| `lag_2d` | Production à J−2 |
| `lag_7d` | Production à J−7 |
| `lag_365d` | Production à la même période de l'année précédente |

Formule générale :

$$
L_t^{(k)}=Y_{t-k}
$$

Avec un pas de 30 minutes et une série régulièrement indexée en UTC, une journée correspond à 48 observations et une semaine à 336 observations.

Il faudra tenir compte des changements d'heure pour comparer les mêmes heures locales.

### Groupe D — Statistiques glissantes

Ces variables décrivent la dynamique récente de la production.

| Feature | Calcul |
|---|---|
| `rolling_mean_7d` | Moyenne des 7 derniers jours |
| `rolling_std_7d` | Écart-type des 7 derniers jours |
| `rolling_q95_30d` | Quantile 95 % des 30 derniers jours |
| `ramp_rate` | Variation entre deux productions successives disponibles |

Moyenne mobile :

$$
\mu_t^{(w)}=\frac{1}{w}\sum_{k=1}^{w}Y_{t-k}
$$

Écart-type mobile :

$$
\sigma_t^{(w)}=
\sqrt{\frac{1}{w-1}\sum_{k=1}^{w}(Y_{t-k}-\mu_t^{(w)})^2}
$$

Variation de production :

$$
\Delta Y_t=Y_{t-1}-Y_{t-2}
$$

Librairie : `pandas` avec `.shift()`, `.rolling()`, `.mean()`, `.std()` et `.quantile()`.

### Groupe E — Croissance du parc photovoltaïque

L'EDA a montré une augmentation importante de la production entre 2024 et 2026.

L'objectif est de construire des variables capables de représenter cette évolution.

| Feature | Calcul |
|---|---|
| `n_sites_solar` | `nb_points_injection` du Parquet |
| `n_sites_growth_30d` | Évolution relative du nombre de sites sur 30 jours |
| `n_sites_growth_yoy` | Évolution relative du nombre de sites sur un an |
| `growth_yoy_q95` | Ratio entre les quantiles élevés de production sur deux périodes comparables |

Croissance du nombre de sites :

$$
G_t^{sites}=\frac{N_t-N_{t-365j}}{N_{t-365j}}
$$

Croissance approximative de la production :

$$
G_t^{Q95}=
\frac{Q_{0.95}(Y_{[t-30j,t)})}
{Q_{0.95}(Y_{[t-395j,t-365j)})+\varepsilon}
$$

Le quantile 95 % permet de limiter l'influence des journées de faible ensoleillement.

Ces ratios restent des indicateurs indirects : ils peuvent également varier avec la météo et la composition des installations.

### Groupe F — Tendance, saisonnalité et résidus

L'objectif est de décomposer la série temporelle en trois composantes :

$$
Y_t=T_t+S_t+R_t
$$

Avec :

- $(T_t)$ : tendance de long terme.
- $(S_t)$ : composante saisonnière.
- $(R_t)$ : résidu non expliqué par la tendance et la saisonnalité.

| Feature | Calcul / Librairie |
|---|---|
| `trend` | Tendance estimée sur l'historique |
| `seasonal` | Composante saisonnière |
| `residual_lag` | Résidu historique retardé |
| `trend_slope_30d` | Pente de la tendance sur 30 jours |

Librairie : `statsmodels.tsa.seasonal.STL` ou `MSTL` pour une série présentant plusieurs saisonnalités.

Il faudra effectuer les décompositions uniquement sur l'historique disponible lors de chaque prévision, pour éviter toute fuite d'information.

## 3. Produit cartésien des groupes de features

On effectue une recherche exhaustive sur les combinaisons des six groupes.

Chaque groupe peut être inclus ou exclu :

$$
\mathcal{C}=\{0,1\}^{6}\setminus\{(0,0,0,0,0,0)\}
$$

Le nombre total de combinaisons non vides est :

$$
N=2^6-1=\boxed{63}
$$

Exemples de combinaisons :

| Combinaison | Groupes |
|---|---|
| 1 | A |
| 2 | A + B |
| 3 | A + C |
| 4 | A + C + E |
| 5 | A + B + C + D |
| 6 | A + B + C + D + E + F |

En Python, on peut utiliser `itertools.product([False, True], repeat=6)` pour générer les combinaisons.

Pour chaque combinaison :

1. Sélectionner les features correspondantes.
2. Entraîner un modèle de référence identique, par exemple LightGBM.
3. Calculer les performances sur une période de validation chronologiquement postérieure à l'entraînement.
4. Enregistrer le $(R^2)$ et les autres métriques.
5. Classer les combinaisons selon leurs performances.

L'horizon de prévision devra être fixé avant les tests. Les features doivent être construites uniquement à partir des informations disponibles à la date d'émission de la prévision.

## 4. Évaluation des performances — R²

Le coefficient de détermination mesure la qualité des prédictions relativement à une prédiction constante égale à la moyenne des observations évaluées.

$$
R^2=1-
\frac{\sum_{i=1}^{n}(y_i-\hat y_i)^2}
{\sum_{i=1}^{n}(y_i-\bar y)^2}
$$

Avec :

- $(y_i)$ : production réelle.
- $(\hat y_i)$ : production prédite.
- $(\bar y)$ : production moyenne sur l'échantillon évalué.

Interprétation :

- $(R^2=1)$ : prédiction parfaite.
- $(R^2=0)$ : performance équivalente à la moyenne de l'échantillon.
- $(R^2<0)$ : performance inférieure à cette référence.

Librairie : `sklearn.metrics.r2_score`.

Il faudra utiliser une **validation chronologique**, idéalement sur plusieurs fenêtres successives, et conserver un jeu de test final non utilisé pour sélectionner les features.

## 5. Points supplémentaires à prendre en compte

### Interactions entre features

Certaines features peuvent être peu informatives individuellement, mais devenir utiles lorsqu'elles sont combinées.

Par exemple, `solar_elevation` peut interagir avec `month`, ou `lag_1d` avec une mesure de croissance du parc.

Il faudra donc évaluer les performances des groupes individuellement, mais également leurs combinaisons, afin d'identifier les interactions utiles.

### Performances nocturnes

La production photovoltaïque est nulle ou très faible pendant une partie importante de la journée.

Ces observations peuvent artificiellement améliorer certaines métriques globales.

Il faudra donc évaluer séparément :

- Le $(R^2)$ global.
- Le $(R^2)$ sur les périodes de production diurne.
- La MAE sur les périodes diurnes.
- Les prédictions positives incorrectes pendant la nuit.

Le $(R^2)$ nocturne peut être non défini lorsque les valeurs observées sont constantes ; la MAE et le taux de fausses productions positives sont alors plus adaptés.


## 6. Résultats attendus

L'objectif final est d'obtenir un tableau comparatif similaire à celui-ci :

| Groupes | Nombre de features | R² validation | MAE validation |
|---|---:|---:|---:|
| A | 6 | À calculer | À calculer |
| A + B | 9 | À calculer | À calculer |
| A + C | 10 | À calculer | À calculer |
| A + C + E | 14 | À calculer | À calculer |
| A + B + C + D + E + F | 24 | À calculer | À calculer |

*Les nombres de features sont indicatifs : ils dépendront des colonnes finalement retenues.*

Cette expérimentation doit permettre de déterminer :

- Quels groupes améliorent le plus la précision des prédictions.
- Quelles combinaisons produisent les meilleurs résultats.
- Si les features de croissance améliorent la stabilité des prédictions dans le temps.
- Si les composantes tendance/saisonnalité/résidus apportent réellement une information supplémentaire.
- Si certaines familles sont redondantes et peuvent être supprimées.

Le résultat attendu est **une sélection argumentée des features pertinentes**, à transmettre à la partie modélisation du projet.

## 7. Fonctions disponibles

Dans `src/enedis/prediction/features.py` :

- A : `create_calendar_features`.
- B : `create_astro_features`.
- C : `create_lag_features`.
- D : `create_rolling_features`.
- E : `create_sites_features`.
- F : `create_decomposition_features`.

`build_production_features` regroupe les fonctions et retourne uniquement les features choisies, sans la cible ni les colonnes brutes. `PRODUCTION_FEATURE_GROUPS` donne les colonnes de chaque groupe : **27 features** pour A à F. Les fonctions individuelles conservent les colonnes d'entrée pour pouvoir être enchaînées.

```python
from enedis.prediction.features import build_production_features

# production : une région, solaire F5, total des puissances P0.
# Coordonnées d'exemple : fixer le point représentatif de la région avant les tests.
features = build_production_features(
    production,
    groups=("A", "B", "C", "D", "E", "F"),
    latitude=48.0,
    longitude=-3.0,
    as_of=date_emission,
)
```

### Entrées et dates

- `horodate` avec fuseau explicite, ou `DatetimeIndex` avec fuseau. Une seule série ; doublons refusés.
- Colonnes par défaut : `total_energie_injectee_wh` et `nb_points_injection`. Utiliser `value_column` et `sites_column` pour d'autres noms. Les features conservent l'unité de la production reçue.
- Grille UTC de 30 minutes, triée. Les créneaux absents sont insérés avec observations manquantes, sans imputation.
- Calendrier local : `timezone="Europe/Paris"` par défaut. `season` est une catégorie à encoder dans le pipeline d'apprentissage. Astronomie : angles en degrés, durée du jour en heures ; approximation par un point régional.
- Lags en jours UTC de 24 heures par défaut. `lag_basis="local"` dans le constructeur, ou `basis="local"` dans `create_lag_features`, cherche la même heure locale. Une heure historique ambiguë ou inexistante donne `NaN`.

### Disponibilité de l'information

- À une ligne cible `t`, les groupes historiques utilisent uniquement les observations strictement antérieures à `t`. Les fenêtres UTC doivent être complètes : 336 valeurs pour 7 jours, 1 440 pour 30 jours. `ramp_rate` compare les deux créneaux précédents.
- `n_sites_solar` utilise le comptage du créneau précédent, pas celui de la cible. Les taux de croissance comparent ce comptage à celui de 30/365 jours auparavant ; une référence nulle donne `NaN`. `growth_yoy_q95` reste le ratio des quantiles défini plus haut, sans soustraire 1.
- `as_of` est une émission de prévision avec fuseau, alignée sur la demi-heure. Les observations à cet instant et après sont masquées pour les calculs historiques. Cela suppose que les observations antérieures sont effectivement disponibles ; tenir compte des délais de publication lors des tests.
- Sans `as_of`, chaque ligne utilise son propre passé : prévision glissante à un pas. Pour plusieurs dates prévues depuis une même émission, fournir `as_of` et les horodates cibles. Les historiques inconnus restent manquants ; une stratégie de prévision à plusieurs pas sera nécessaire.

### Décomposition F

STL est réajusté quotidiennement à minuit UTC sur les **30 jours précédents complets**, avec une période de 48 demi-heures. Paramètres : `decomposition_period`, `decomposition_history_days`, `decomposition_refit_every` dans le constructeur.

La dernière tendance est extrapolée selon sa pente sur 30 jours ; le dernier cycle saisonnier est répété. `residual_lag` utilise le résidu du créneau précédent. `trend_slope_30d` est exprimé en unité de production par jour. Aucun ajustement n'utilise des données postérieures à sa coupure historique, plafonnée par `as_of`.

Historique insuffisant ou trou dans la fenêtre STL : features F manquantes. Les features annuelles et le ratio Q95 nécessitent respectivement au moins 365 et 395 jours de recul. Lors de la comparaison des 63 combinaisons, conserver des observations de validation communes pour rendre les scores comparables.

Vérification sur les 52 608 lignes brutes bretonnes : 27 features calculées, sans modification des observations. Aucun intervalle de 30 jours n'est entièrement renseigné : les Q95 glissants et les features F restent manquants. Le traitement de ces fenêtres doit être fixé avec le module 1 avant une recherche incluant ces groupes.

API utilisées : [position solaire pvlib](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.solarposition.get_solarposition.html), [lever/coucher pvlib](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.solarposition.sun_rise_set_transit_spa.html), [STL statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.tsa.seasonal.STL.html).
