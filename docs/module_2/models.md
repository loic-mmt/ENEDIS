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
