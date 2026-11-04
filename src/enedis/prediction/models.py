"""Local Kumo regression adapter and shared single-target prediction interface."""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.utils.validation import check_is_fitted

from .utils import (
    check_choice, check_collection, check_column, check_dataframe,
    check_datetime_index, check_feature_columns, check_feature_type,
    check_integer, check_predictions, check_regression_target, check_timestamp,
)


def _ordered_features(model, X: pd.DataFrame) -> pd.DataFrame:
    expected = getattr(model, "feature_names_in_", None)
    check_feature_columns(X, expected)
    if expected is not None:
        return X.loc[:, list(expected)]  # Ordre des colonnes utilisé au fit.

    return X


def predict(model, X: pd.DataFrame) -> pd.Series:
    """Call any fitted single-output regressor; preserve query order and index.

    X contains features only. NaN estimates remain missing for coverage scoring.
    No fitting, feature construction or file access occurs here.
    """
    X = _ordered_features(model, X)
    if not callable(getattr(model, "predict", None)):
        raise TypeError("Le modèle doit fournir une méthode predict(X).")

    values = check_predictions(model.predict(X), X.index)

    return pd.Series(values, index=X.index, name="prediction")


def _load_kumo():
    # Heavy optional dependencies: other regressors work without this SDK.
    try:
        import torch
        import sdm
    except ImportError as exc:
        raise ImportError("Kumo nécessite : python -m pip install -r requirements-kumo.txt") from exc

    return torch, sdm


class KumoTabularRegressor(RegressorMixin, BaseEstimator):
    """sklearn-style interface to pretrained Kumo Tabular (local inference).

    fit caches labelled context; it does not optimize pretrained weights.
    Missing targets are excluded. Context keeps the latest observed rows,
    ordered by datetime index when provided, otherwise by input row order.
    Query estimates use the predictive median q500, in the target's units.
    """

    def __init__(self, *, size="large", device="auto", num_estimators=8,
                 context_size=2048, batch_size=256, random_state=42):
        self.size = size
        self.device = device
        self.num_estimators = num_estimators
        self.context_size = context_size
        self.batch_size = batch_size
        self.random_state = random_state

    def __sklearn_is_fitted__(self):
        return getattr(self, "_fitted", False)

    def _table(self, X, *, fitting=False):
        data = X.reset_index(drop=True).copy()  # L'horodate ne devient pas une feature.
        stypes = {}

        for column in data:
            series = data[column]
            expected = None if fitting else self.feature_stypes_[column]  # Types fixés au fit.
            stypes[column] = check_feature_type(series, expected)
            if stypes[column] == "numerical":
                data[column] = series.to_numpy(dtype=float, na_value=np.nan)
            else:
                data[column] = series.astype("string")

        table = self._sdm.TableTensor.from_pandas(data, stypes=stypes, device=self.device_)
        if fitting:
            self.feature_stypes_ = stypes

        return table

    def _autocast(self):
        return self._torch.amp.autocast(
            self.device_.type, dtype=self._torch.float16,
            enabled=self.device_.type == "cuda",
        )

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """Prepare context supplied by the caller, already filtered/masked."""
        self._fitted = False  # Un fit échoué invalide l'ancien contexte.
        check_feature_columns(X)

        for name in ("num_estimators", "batch_size"):
            check_integer(getattr(self, name), name, minimum=1)

        if self.context_size is not None:
            check_integer(self.context_size, "context_size", minimum=2)
        check_choice(self.size, ("small", "medium", "large"), "size")
        check_integer(self.random_state, "random_state")
        check_regression_target(X, y)

        X, y = X.loc[y.notna()], y.loc[y.notna()]  # Cibles observées uniquement.
        self.n_available_ = len(y)

        if isinstance(X.index, pd.DatetimeIndex):
            check_datetime_index(X.index, "Horodates du contexte", aware=False)
            order = np.argsort(X.index.asi8, kind="stable")
            X, y = X.iloc[order], y.iloc[order]
        if self.context_size is not None:
            # Garder les observations les plus récentes.
            X, y = X.iloc[-self.context_size:], y.iloc[-self.context_size:]

        self._torch, self._sdm = _load_kumo()
        self.device_ = self._torch.device(
            "cuda" if self._torch.cuda.is_available() else "cpu"
        ) if self.device == "auto" else self._torch.device(self.device)
        x_table = self._table(X, fitting=True)

        # Separate tables prevent the target from leaking into the inputs.
        y_table = self._sdm.TableTensor.from_pandas(
            pd.DataFrame({"target": y.to_numpy(dtype=float)}),
            stypes={"target": "numerical"}, device=self.device_,
        )

        backend_key = (self.size, str(self.device_))
        if getattr(self, "_backend_key", None) != backend_key:
            self.model_ = self._sdm.models.KumoTabular(task="regression", size=self.size, device=self.device_)
            self._backend_key = backend_key
        else:
            self.model_.clear()  # Effacer le contexte, conserver les poids.

        self.model_.eval()
        generator = self._torch.Generator(device=self.device_).manual_seed(self.random_state)

        with self._torch.inference_mode(), self._autocast():  # Aucun gradient à calculer.
            self.model_.fit(x_table, y_table, num_estimators=self.num_estimators,
                            estimator_batch_size=1, generator=generator)

        self.feature_names_in_ = np.array(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        self.context_index_ = X.index.copy()
        self.n_context_ = len(X)
        self._fitted = True

        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict in bounded batches without updating the fitted context."""
        check_is_fitted(self)
        X = _ordered_features(self, X)
        check_integer(self.batch_size, "batch_size", minimum=1)

        values = []
        with self._torch.inference_mode(), self._autocast():
            for start in range(0, len(X), self.batch_size):
                output = self.model_.predict(self._table(X.iloc[start:start + self.batch_size]))
                median = output.select_columns(["q500"]).cpu().to_pandas()["q500"]  # q500 = médiane prédictive.
                values.append(median.to_numpy(dtype=float))

        return np.concatenate(values) if values else np.empty(0, dtype=float)  # shape: (len(X),)


def KumoTabular_model(df: pd.DataFrame, target: str = "target", *,
                     feature_columns=None, as_of=None, **model_options) -> KumoTabularRegressor:
    """Return fitted Kumo; optionally restrict context to timestamps < as_of.

    df contains features and one target. Pass feature_columns explicitly when
    other targets/metadata coexist. Already-built features must themselves be
    causal; an as_of filter cannot undo leakage inside their values.
    """
    check_dataframe(df, min_columns=1, string_columns=True, type_error=ValueError)
    check_column(df, target, "Colonne cible")
    if as_of is not None:
        cutoff = check_timestamp(as_of)
        check_datetime_index(df.index, unique=False)
        df = df.loc[df.index < cutoff]  # L'instant d'émission lui-même est exclu.

    columns = check_collection(
        df.columns.drop(target) if feature_columns is None else feature_columns,
        "feature_columns", choices=df.columns.drop(target),
    )

    return KumoTabularRegressor(**model_options).fit(df.loc[:, columns], df[target])
