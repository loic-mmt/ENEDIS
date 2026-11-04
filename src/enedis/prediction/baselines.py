import pandas as pd
import numpy as np

from .utils import check_column, check_finite, check_integer, check_numeric, verify_last_date


def persistance_baseline(df: pd.DataFrame, target: str, date_column: str, last_date, horizon: int) -> np.ndarray:
    """Repeat the last observed target for `horizon` annual steps.

    Input must describe ONE commune, already ordered chronologically and limited
    to last_date by the caller. Missing targets are skipped; an entirely missing
    target produces NaN predictions. No filtering or mutation is performed.
    """
    check_integer(horizon, "horizon", minimum=1)
    check_column(df, target, "Colonne cible")
    verify_last_date(df, date_column, last_date)

    variable = df[target]
    check_numeric(variable, target, allow_bool=True, allow_complex=True, finite=False)

    observed = variable.dropna()
    value = float(observed.iloc[-1]) if not observed.empty else np.nan

    if not observed.empty:
        check_finite(value, "Dernière valeur observée")

    return np.full(horizon, value, dtype=float)  # shape: (horizon,) ; NaN si aucun historique connu.


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
    check_integer(info_length, "info_length", minimum=2)

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
    observed = df[target].dropna().to_numpy(dtype=float)  # Même sélection que years[mask].
    check_finite(observed, "Valeurs observées")
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
    check_finite(predictions, "Prévisions de tendance")

    return np.maximum(predictions, 0.0)  # Consommation et puissance restent non négatives.
