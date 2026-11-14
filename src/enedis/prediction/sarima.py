"""Seasonal ARIMA regressors with the shared fit(X, y)/predict(X) interface."""

import warnings

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted
from threadpoolctl import threadpool_limits

from .utils import (
    check_aligned_series,
    check_choice,
    check_dataframe,
    check_datetime_index,
    check_feature_columns,
    check_finite,
    check_integer,
    check_numeric,
)


class SARIMARegressor(RegressorMixin, BaseEstimator):
    """SARIMA on a UTC half-hourly grid, without exogenous features.

    Default (1,0,1)(1,1,1,48): AR/MA dynamics and a daily seasonal difference.
    X supplies timestamps only. Missing historical slots are restored as NaN,
    then handled by the state-space likelihood without interpolation. Full
    state-space differencing keeps forecasts in the original target unit.
    """

    uses_features = False

    def __init__(self, *, order=(1, 0, 1), seasonal_order=(1, 1, 1, 48), trend="n", maxiter=100):
        self.order = order
        self.seasonal_order = seasonal_order
        self.trend = trend
        self.maxiter = maxiter

    def __sklearn_is_fitted__(self):
        return getattr(self, "_fitted", False)

    def _check_orders(self):
        for name, length in (("order", 3), ("seasonal_order", 4)):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or len(values) != length:
                raise ValueError(f"{name} doit contenir {length} entiers.")
            for value in values:
                check_integer(value, name, minimum=0)

        period = self.seasonal_order[3]
        if period == 1 or any(self.seasonal_order[:3]) and period < 2:
            raise ValueError("Une saisonnalité active nécessite une période supérieure ou égale à 2.")
        check_choice(self.trend, (None, "n", "c", "t", "ct"), "trend")
        check_integer(self.maxiter, "maxiter", minimum=1)

    def _fit_exog(self, X, y, grid):
        return None  # SARIMA ignore les colonnes de X.

    def _predict_exog(self, X, grid):
        return None

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """Fit only the supplied past labels; preserve elapsed-time spacing."""
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        self._fitted = False
        self._check_orders()
        check_dataframe(X, "X", nonempty=True, string_columns=True)
        check_datetime_index(X.index, ordered=True, nonempty=True, step="30min")
        check_aligned_series(y, X.index)
        check_numeric(y, "Cible SARIMA", allow_empty=False)

        known = y.dropna()
        period = self.seasonal_order[3] if any(self.seasonal_order[:3]) else 1
        if len(known) < max(3, 2 * period):
            raise ValueError("SARIMA nécessite au moins deux cycles observés pour cette saisonnalité.")

        index = X.index.tz_convert("UTC")
        grid = pd.date_range(index[0], index[-1], freq="30min", name="horodate")
        history = pd.Series(y.to_numpy(dtype=float, na_value=np.nan), index=index).reindex(grid)
        exog = self._fit_exog(X, y, grid)

        # Échelle estimée sur le contexte seul ; sortie reconvertie dans l'unité source.
        scale = float(known.std(ddof=0))
        self.scale_ = scale if scale > 0 else max(float(known.abs().max()), 1.)

        self.model_ = SARIMAX(
            history / self.scale_, exog=exog,
            order=tuple(self.order), seasonal_order=tuple(self.seasonal_order),
            trend=self.trend, simple_differencing=False,
            enforce_stationarity=False, enforce_invertibility=False,
        )

        with warnings.catch_warnings(record=True) as recorded, threadpool_limits(limits=1):
            warnings.simplefilter("always")
            self.result_ = self.model_.fit(disp=False, maxiter=self.maxiter, cov_type="none", low_memory=True)

        check_finite(self.result_.params, "Paramètres SARIMA")

        self.fit_warnings_ = [str(warning.message) for warning in recorded]
        self.converged_ = bool(self.result_.mle_retvals.get("converged", False))
        self.iterations_ = int(self.result_.mle_retvals.get("iterations", 0))

        self.feature_names_in_ = np.array(X.columns, dtype=object)
        self.n_features_in_ = X.shape[1]

        self.context_index_ = index[y.notna().to_numpy()].copy()
        self.n_context_ = len(known)
        self.n_time_steps_ = len(grid)
        self.last_date_ = grid[-1]
        self._fitted = True

        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Forecast requested future slots, including intervening missing slots."""
        check_is_fitted(self)
        check_dataframe(X, "X", string_columns=True)
        check_datetime_index(X.index, ordered=True, step="30min")

        if len(X) == 0:
            return np.empty(0, dtype=float)

        dates = X.index.tz_convert("UTC")
        steps = np.asarray((dates - self.last_date_) / pd.Timedelta(minutes=30), dtype=int)
        if (steps <= 0).any():
            raise ValueError("SARIMA prédit uniquement des dates strictement postérieures au contexte.")
        grid = pd.date_range(self.last_date_ + pd.Timedelta(minutes=30), dates[-1], freq="30min")
        exog = self._predict_exog(X, grid)

        with threadpool_limits(limits=1):
            forecasts = np.asarray(self.result_.forecast(steps=int(steps.max()), exog=exog), dtype=float) * self.scale_

        selected = forecasts[steps - 1]  # Ne pas comprimer le temps si les dates demandées sont espacées.
        check_finite(selected, "Prévisions SARIMA")

        return selected


class SARIMAXRegressor(SARIMARegressor):
    """SARIMA with numerical/categorical covariates available at forecast time.

    Fit medians, scaling and category encoding on past observed labels only.
    Missing exogenous values are filled locally; missing targets stay NaN.
    predict requires every half-hour between the context and the last query.
    """

    uses_features = True
    requires_future_features = True

    def _feature_frame(self, X):
        frame = X.loc[:, self.feature_names_in_].copy()

        for column in self.numeric_features_:
            check_numeric(frame[column], f"Feature {column}", allow_bool=True)
            frame[column] = frame[column].to_numpy(dtype=float, na_value=np.nan)

        for column in self.categorical_features_:
            frame[column] = frame[column].astype("string").fillna("__missing__").astype(object)

        return frame

    def _fit_exog(self, X, y, grid):
        check_feature_columns(X)
        self.feature_names_in_ = np.array(X.columns, dtype=object)
        self.numeric_features_ = X.select_dtypes(include=["number", "bool"]).columns.tolist()
        self.categorical_features_ = [name for name in X if name not in self.numeric_features_]
        frame = self._feature_frame(X)

        self.preprocessor_ = ColumnTransformer([
            ("numeric", make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True),
                StandardScaler(),
            ), self.numeric_features_),
            ("categorical", OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False),
             self.categorical_features_),
        ], sparse_threshold=0)

        encoded = self.preprocessor_.fit_transform(frame.loc[y.notna()])  # Aucun apprentissage sur le futur.
        self.active_features_ = np.var(encoded, axis=0) > 1e-12  # Constantes et lags entièrement absents écartés.
        self.n_exog_ = int(self.active_features_.sum())

        frame.index = frame.index.tz_convert("UTC")

        return self._transform_exog(frame.reindex(grid))

    def _transform_exog(self, frame):
        if self.n_exog_ == 0:
            return None

        with warnings.catch_warnings():
            # Catégorie inconnue prévue par l'encodeur : vecteur nul, sans avertissement répété.
            warnings.filterwarnings("ignore", message="Found unknown categories.*", category=UserWarning,
                                    module="sklearn.preprocessing._encoders")
            encoded = self.preprocessor_.transform(self._feature_frame(frame))[:, self.active_features_]

        check_finite(encoded, "Features SARIMAX")

        return pd.DataFrame(encoded, index=frame.index)

    def _predict_exog(self, X, grid):
        check_feature_columns(X, self.feature_names_in_)
        if not X.index.tz_convert("UTC").equals(grid):
            raise ValueError("SARIMAX nécessite les features de chaque demi-heure après le contexte jusqu'à la prévision.")

        frame = X.copy()
        frame.index = frame.index.tz_convert("UTC")

        return self._transform_exog(frame)
