import pandas as pd
import numpy as np
from numbers import Integral

from .utils import verify_last_date


def persistance_baseline(
    df: pd.DataFrame, target: str, date_column: str, last_date, horizon: int
) -> np.ndarray:
    """Repeat the last observed target for `horizon` annual steps.

    Input must describe ONE commune, already ordered chronologically and limited
    to last_date by the caller. Missing targets are skipped; an entirely missing
    target produces NaN predictions. No filtering or mutation is performed.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, Integral) or horizon <= 0:
        raise ValueError("horizon doit être un entier strictement positif.")
    if not isinstance(target, str) or target not in df.columns:
        raise ValueError(f"Colonne cible absente ou invalide : {target}")

    verify_last_date(df, date_column, last_date)

    variable = df[target]

    if not isinstance(variable, pd.Series):
        raise ValueError(f"Colonne cible dupliquée : {target}")
    if not pd.api.types.is_numeric_dtype(variable.dtype) and variable.notna().any():
        raise ValueError(f"La cible {target} doit être numérique.")

    observed = variable.dropna()
    value = float(observed.iloc[-1]) if not observed.empty else np.nan

    if not observed.empty and not np.isfinite(value):
        raise ValueError("La dernière valeur observée doit être finie.")

    return np.full(horizon, value, dtype=float)


def linear_baseline(
    df: pd.DataFrame,
    target: str,
    date_column: str,
    last_date,
    horizon: int,
    info_length: int,
) -> np.ndarray:
    """Fit an annual linear trend on the last info_length valid observations.

    Input describes ONE commune in chronological order, limited to last_date.
    Forecast years are last_date's year + 1 through + horizon. Actual year gaps
    are respected. Calendar dates must represent at most one observation per
    year. Missing targets are skipped; fewer than two valid observations fall
    back to persistence. Forecasts are clipped at zero for energy/capacity targets.
    The input is never modified.
    """
    if isinstance(info_length, bool) or not isinstance(info_length, Integral) or info_length < 2:
        raise ValueError("info_length doit être un entier supérieur ou égal à 2.")

    # Reuse target, horizon and cutoff validation, and the fallback predictions.
    fallback = persistance_baseline(df, target, date_column, last_date, horizon)
    dates = df[date_column]
    if pd.api.types.is_integer_dtype(dates.dtype) or dates.astype("string").str.fullmatch(r"\d{4}").all():
        years = pd.to_numeric(dates).to_numpy(dtype=float)
        origin = int(last_date)
    else:
        # Keep each timestamp's local calendar year, including explicit offsets.
        years = np.array([pd.Timestamp(value).year for value in dates], dtype=float)
        origin = pd.Timestamp(last_date).year
    if np.any(np.diff(years) <= 0):
        raise ValueError("Historique annuel attendu : années uniques, en ordre croissant.")

    mask = df[target].notna().to_numpy()
    observed = df[target].dropna().to_numpy(dtype=float)
    if not np.isfinite(observed).all():
        raise ValueError("Les valeurs observées doivent être finies.")
    if len(observed) < 2:
        return fallback

    # example : x = [2022, 2023, 2024], y = [100, 110, 120]
    x = years[mask][-info_length:]
    y = observed[-info_length:]

    # Centering avoids numerical instability from large calendar year values.
    # mean = 2023 → centered = [-1, 0, 1]
    centered = x - x.mean()

    # slope = sum((x_i - x_hat)(y_i - y_hat)) / sum((x_i - x_hat)^2)
    slope = np.dot(centered, y - y.mean()) / np.dot(centered, centered)

    # with origin = 2024, horizon = 3 → [2025, 2026, 2027]
    future_years = origin + np.arange(1, horizon + 1, dtype=float)

    predictions = y.mean() + slope * (future_years - x.mean())
    if not np.isfinite(predictions).all():
        raise ValueError("La tendance produit des prévisions non finies.")
    return np.maximum(predictions, 0.0)
