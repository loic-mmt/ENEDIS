# Modèles de régression

`src/enedis/prediction/models.py` fournit :

- `KumoTabular_model(df, target, ...)` : prépare un modèle Kumo et le retourne.
- `KumoTabularRegressor` : même modèle avec l'interface `fit(X, y)` / `predict(X)` de sklearn.
- `predict(model, X)` : appelle tout modèle de régression à une cible muni de `.predict(X)` ; retourne une Series nommée `prediction`, avec l'index de `X`.

## Kumo Tabular

Installation depuis la racine du projet :

```bash
python -m pip install -r requirements.txt -r requirements-kumo.txt
```

Kumo est préentraîné : `fit` prépare et met en cache le contexte étiqueté, sans modifier les poids. Le premier appel avec les poids préentraînés nécessite leur téléchargement. Exécution locale, sur CUDA si disponible, sinon CPU.

```python
from enedis.prediction.models import KumoTabular_model, predict

# train : features et cible ; X_query : uniquement les mêmes features.
# Les deux tables proviennent des données masquées de l'expérience.
model = KumoTabular_model(
    train,
    target="energie_mwh",
    feature_columns=feature_columns,
    as_of=gap_start,
    context_size=2048,
    num_estimators=8,
)
estimates = predict(model, X_query[feature_columns])
```

- `as_of` : seules les lignes strictement antérieures sont utilisables ; index et limite avec fuseau horaire. Pour une prévision ou une reconstruction vers l'avant, utiliser le début du bloc masqué. Les features doivent aussi être calculées sans information future.
- Cibles manquantes : exclues du contexte. Features numériques manquantes et catégories : confiées au prétraitement du SDK, appris sur le contexte.
- `context_size=2048` : conserve les dernières observations connues, triées par horodate si l'index est temporel. Plafond mémoire initial, à comparer en validation ; `None` utilise tout le contexte fourni.
- `batch_size=256` : taille des lots de requêtes. Aucun réentraînement pendant `predict`.
- Sortie : médiane prédictive `q500`, dans l'unité de la cible ; aucune conversion ni contrainte de positivité automatique. Ce n'est pas un intervalle de confiance.
- Un nouveau `.fit(X, y)` sur le même adaptateur remplace le contexte et réutilise les poids si la taille et le périphérique restent identiques.

Fournir explicitement `feature_columns` si la table contient des métadonnées ou d'autres cibles. Ne jamais fournir les réponses cachées de `truth.parquet` au modèle. Pour sklearn, préparer également ses transformations dans une Pipeline ajustée sur le contexte uniquement.

API : [KumoTabular](https://nvidia.github.io/structured-data-models/api/generated/sdm.models.KumoTabular.html), [fit / predict](https://nvidia.github.io/structured-data-models/api/generated/sdm.models.ICLModel.html).

## Autres modèles

```python
from sklearn.linear_model import LinearRegression

model = LinearRegression().fit(X_train, y_train)
estimates = predict(model, X_query)
```

`X_query` ne contient pas la cible. Les colonnes sont remises dans l'ordre du `fit` si le modèle expose `feature_names_in_` ; colonnes manquantes ou supplémentaires refusées. Une seule valeur numérique par ligne est attendue. Les prédictions NaN restent manquantes pour mesurer la couverture.

## Premier essai de remplissage : validation, marche avant, A+B+C

`reconstruct_with_model` dans `src/enedis/prediction/imputation_models.py` relie les données masquées, les features et le modèle.

```python
from enedis.prediction.imputation_evaluation import load_evaluation_split, score_reconstruction
from enedis.prediction.imputation_models import reconstruct_with_model

inputs, truth, gaps = load_evaluation_split(evaluation_dir, "validation")
predictions, diagnostics = reconstruct_with_model(
    inputs, gaps,
    latitude=48.170199, longitude=-2.956569,  # Point breton retenu pour le test.
    context_size=2048,
)
scores = score_reconstruction(
    truth, predictions["prediction_wh"], weight_column="duration_weight",
)
```

- Kumo par défaut ; `model=...` accepte un autre régresseur avec `fit(X, y)` et `predict(X)`. L'instance est réajustée à chaque trou ; Kumo réutilise ses poids.
- Validation uniquement : les autres splits sont refusés. Les lignes à partir de la fin de phase sont exclues.
- A+B+C par défaut : 15 features, dont les lags de production à J−1, J−2, J−7 et J−365. Les jours correspondent à 24 h UTC. `groups=("A", "B")` conserve les 11 features initiales pour comparaison.
- Les lags sont calculés sur les observations connues, après application de tous les masques. Une référence absente ou située dans un trou reste NaN ; aucune prédiction ne sert à construire C.
- Pour chaque trou : dernières observations connues strictement avant son début, au maximum `context_size`. Les zéros restent des observations ; `is_observed=False` exclut une valeur même si elle est renseignée.
- Tout le bloc est prédit avec ce même contexte. Les estimations ne deviennent jamais des observations pour les trous suivants.
- `predictions` : une ligne par demi-heure masquée, index UTC, `prediction_wh`, identifiant du trou, modèle et coupure historique. `prediction_wh` est bornée à zéro et utilisée pour les scores ; `prediction_raw_wh` conserve les estimations avant clipping. Les NaN restent manquants, sans conversion d'unité.
- `diagnostics` : une ligne par trou, contexte disponible (`n_available`), fourni au fit (`n_train`), utilisé si exposé par le modèle (`n_context`), bornes du contexte, nombre de valeurs clippées (`n_clipped`) et durées du fit/de la prédiction en secondes.
- `on_gap_end` : callback facultatif recevant une copie des diagnostics après chaque trou ; utilisé pour l'avancement dans le terminal.
- Moins de `min_observations=2` observations utilisables : prédictions NaN, statut `insufficient_context`. `partial_prediction` indique des estimations partiellement ou entièrement manquantes après prédiction. Les autres erreurs du modèle sont remontées.

La fonction ne lit ni n'écrit de fichier et ne reçoit pas `truth`. Le script `scripts/module_2/impute_data.py` se charge des scores et des exports : voir [le premier test Kumo](imputation.md#premier-test-kumo). Cet exemple déclenche le téléchargement des poids au premier vrai fit Kumo ; les tests automatiques utilisent des modèles locaux légers.
