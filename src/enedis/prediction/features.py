from collections.abc import Iterable
from functools import wraps

import numpy as np
import pandas as pd

from .contracts import TARGET_COLUMNS, validate_history
from .utils import (
    check_choice, check_collection, check_column, check_dataframe,
    check_datetime_index, check_integer, check_numeric, check_real, check_timestamp,
)


def build_features(
    history: pd.DataFrame,
    target: str,
    lags: Iterable[int] = (1, 2, 3),
    rolling_window: int = 3,
) -> pd.DataFrame:
    """Build annual features for one target, independently for each commune.

    Return one row per existing commune/year, preserving input order and index.
    `annee` is the forecast origin: all features use values from that year or
    earlier, assuming the origin year's observation is available at forecast time.
    Only the identifiers and generated features are returned; no future labels or
    arbitrary extra input columns are included. Input must follow validate_history.

    Columns are prefixed with target:
      current: observed value at the origin, kept missing if unavailable;
      lag_N: value exactly N calendar years earlier, not N rows earlier;
      change_1y: current minus the previous calendar year's value;
      mean_Wy: mean over [origin - W + 1, origin], requiring W observed values;
      count_Wy: number of nonmissing observations within that same window.

    Missing years/values are not filled, and no new origin rows are created.
    Empty lags are allowed. Scaling, imputation and future label construction
    belong to later training steps. The input is never modified.
    """
    check_choice(target, TARGET_COLUMNS, "target")
    offsets = check_collection(lags, "lags", integers=True, minimum=1, allow_empty=True)
    check_integer(rolling_window, "rolling_window", minimum=1)
    validate_history(history)

    # Les clés géographiques et annuelles empêchent tout mélange entre communes.
    communes = history["code_commune"].to_numpy()
    years = history["annee"].to_numpy(dtype=np.int64)
    values = history[target].to_numpy(dtype=float, na_value=np.nan)
    source = pd.Series(values, index=pd.MultiIndex.from_arrays([communes, years]))
    lagged = {0: values}
    needed = set(offsets) | set(range(rolling_window)) | {1}  # Retards + fenêtre + variation annuelle.

    for offset in sorted(needed - {0}):
        # Une année absente donne NaN, même si une ligne plus ancienne existe.
        keys = pd.MultiIndex.from_arrays([communes, years - offset])
        lagged[offset] = source.reindex(keys).to_numpy(dtype=float)

    result = history[["code_commune", "annee"]].copy()
    result[f"{target}_current"] = values

    for offset in offsets:
        result[f"{target}_lag_{offset}"] = lagged[offset]

    result[f"{target}_change_1y"] = values - lagged[1]

    # Fenêtre calendaire complète : aucune moyenne partielle masquée.
    window = np.column_stack([lagged[offset] for offset in range(rolling_window)])  # shape: (n_lignes, rolling_window)
    result[f"{target}_mean_{rolling_window}y"] = window.mean(axis=1)
    result[f"{target}_count_{rolling_window}y"] = np.isfinite(window).sum(axis=1)

    return result


PRODUCTION_FEATURE_GROUPS = {
    "A": ("hour_sin", "hour_cos", "doy_sin", "doy_cos", "month", "week_of_year", "season", "day_of_week"),
    "B": ("solar_elevation", "solar_azimuth", "daylight_duration"),
    "C": ("lag_1d", "lag_2d", "lag_7d", "lag_365d"),
    "D": ("rolling_mean_7d", "rolling_std_7d", "rolling_q95_30d", "ramp_rate"),
    "E": ("n_sites_solar", "n_sites_growth_30d", "n_sites_growth_yoy", "growth_yoy_q95"),
    "F": ("trend", "seasonal", "residual_lag", "trend_slope_30d"),
}
HALF_HOUR = pd.Timedelta(minutes=30)
SLOTS_PER_DAY = 48


def _aware_index(values) -> pd.DatetimeIndex:
    """Convert explicit offsets/timezones to UTC, refusing ambiguous naive dates."""
    try:
        if pd.api.types.is_numeric_dtype(values.dtype):
            raise ValueError("Les horodates doivent être des dates avec fuseau explicite.")
        if not isinstance(values.dtype, pd.DatetimeTZDtype):
            if any(pd.Timestamp(value).tzinfo is None for value in values):
                raise ValueError("Les horodates doivent préciser leur fuseau horaire.")

        dates = pd.DatetimeIndex(pd.to_datetime(values, utc=True, format="mixed", errors="raise"))
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError("Horodates invalides ou sans fuseau horaire explicite.") from error

    check_datetime_index(dates, unique=False, step="30min")

    return dates


def _production_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One already filtered series; regular UTC grid with missing observations left missing."""
    check_dataframe(df, nonempty=True)
    if "horodate" in df:
        dates = _aware_index(df["horodate"])
        result = df.drop(columns="horodate").copy()
    elif isinstance(df.index, pd.DatetimeIndex):
        dates = _aware_index(df.index)
        result = df.copy()
    else:
        raise ValueError("Une colonne horodate ou un DatetimeIndex est nécessaire.")
    check_datetime_index(dates)

    for column in ("code_region", "filiere_de_production", "plage_de_puissance_injection"):
        if column in result and result[column].nunique(dropna=True) > 1:
            raise ValueError(f"Plusieurs séries présentes dans {column} ; filtrer avant les features.")

    result.index = dates.rename("horodate")
    result = result.sort_index()
    grid = pd.date_range(result.index[0], result.index[-1], freq="30min", name="horodate")

    return result.reindex(grid)  # Créneaux absents ajoutés avec NaN, sans remplissage.


def _prepare_frame(function):
    @wraps(function)
    def create(df, *args, **kwargs):
        return function(_production_frame(df), *args, **kwargs)

    return create


def _cutoff(as_of) -> pd.Timestamp | None:
    if as_of is None:
        return None

    return check_timestamp(as_of, step="30min")


def _observed(frame, column, as_of=None, *, integer=False):
    check_column(frame, column)
    values = frame[column]
    check_numeric(values, column, minimum=0, integer=integer)
    series = pd.Series(values.to_numpy(dtype=float, na_value=np.nan), index=frame.index)
    limit = _cutoff(as_of)

    # as_of est l'émission : le créneau qui commence à cet instant n'est pas encore observé.
    return series.where(series.index < limit) if limit is not None else series


def _lag(series, days, *, basis="utc", timezone="Europe/Paris"):
    check_choice(basis, ("utc", "local"), "basis")
    if basis == "utc":
        keys = series.index - pd.Timedelta(days=days)
    else:
        wall_time = series.index.tz_convert(timezone).tz_localize(None) - pd.DateOffset(days=days)
        # Une heure locale ambiguë ou inexistante n'a pas de correspondant unique.
        keys = wall_time.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")

    return series.reindex(keys).to_numpy(dtype=float)


def _ratio(numerator, denominator):
    """Unavailable growth when the reference is zero, missing or overflows."""
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        values = np.asarray(numerator, dtype=float) / np.asarray(denominator, dtype=float)

    return np.where(np.isfinite(values) & (np.asarray(denominator) > 0), values, np.nan)


@_prepare_frame
def create_calendar_features(df: pd.DataFrame, *, timezone="Europe/Paris") -> pd.DataFrame:
    """Group A. Calendar of the target instant in local time, on a regular UTC index.

    Keep input columns. Insert missing half-hours without filling observations.
    season is categorical (winter/spring/summer/autumn), to encode in training.
    """
    result = df
    local = result.index.tz_convert(timezone)
    hours = local.hour + local.minute / 60.
    doy = local.dayofyear + hours / 24.

    result["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    result["hour_cos"] = np.cos(2 * np.pi * hours / 24)  # Sin/cos : 23 h reste proche de 0 h.
    result["doy_sin"] = np.sin(2 * np.pi * doy / 365.2425)
    result["doy_cos"] = np.cos(2 * np.pi * doy / 365.2425)
    result["month"] = local.month
    result["week_of_year"] = local.isocalendar().week.to_numpy(dtype=int)
    result["day_of_week"] = local.dayofweek

    seasons = np.select([np.isin(local.month, [3, 4, 5]), np.isin(local.month, [6, 7, 8]),
                         np.isin(local.month, [9, 10, 11])], ["spring", "summer", "autumn"], default="winter")
    result["season"] = pd.Categorical(seasons, categories=["winter", "spring", "summer", "autumn"])

    return result


@_prepare_frame
def create_astro_features(
    df: pd.DataFrame, latitude: float, longitude: float, *, timezone="Europe/Paris",
) -> pd.DataFrame:
    """Group B. Representative point: angles in degrees, daylight duration in hours.

    Calculations use pvlib, without network requests or weather observations.
    Polar dates without defined sunrise/sunset keep a missing duration.
    """
    for name, value, lower, upper in (("latitude", latitude, -90, 90), ("longitude", longitude, -180, 180)):
        check_real(value, name, minimum=lower, maximum=upper)

    from pvlib import solarposition

    result = df
    position = solarposition.get_solarposition(result.index, latitude, longitude)
    result["solar_elevation"] = position["elevation"]
    result["solar_azimuth"] = position["azimuth"]

    dates = result.index.tz_convert(timezone).tz_localize(None).normalize()
    unique_dates = dates.unique()
    localized = unique_dates.tz_localize(timezone, nonexistent="shift_forward", ambiguous=True)
    events = solarposition.sun_rise_set_transit_spa(localized, latitude, longitude)
    duration = (events["sunset"] - events["sunrise"]).dt.total_seconds() / 3600
    by_day = pd.Series(duration.to_numpy(), index=unique_dates)
    result["daylight_duration"] = by_day.reindex(dates).to_numpy()

    return result


@_prepare_frame
def create_lag_features(
    df: pd.DataFrame, value_column="total_energie_injectee_wh", *,
    basis="utc", timezone="Europe/Paris", as_of=None,
) -> pd.DataFrame:
    """Group C. Exact 1/2/7/365-day lookups; never shift by existing row count.

    utc means elapsed 24-hour days. local means the same wall-clock hour on an
    earlier local date; ambiguous/nonexistent historical hours return NaN.
    as_of excludes observations at/after a fixed forecast issuance, if supplied.
    """
    result = df
    observed = _observed(result, value_column, as_of)

    for days in (1, 2, 7, 365):
        result[f"lag_{days}d"] = _lag(observed, days, basis=basis, timezone=timezone)

    return result


@_prepare_frame
def create_rolling_features(
    df: pd.DataFrame, value_column="total_energie_injectee_wh", *, as_of=None,
) -> pd.DataFrame:
    """Group D. Strictly past UTC windows, requiring every expected observation.

    7 days = 336 half-hours; 30 days = 1440. std uses ddof=1.
    ramp_rate = Y[t-30min] - Y[t-60min], not Y[t] - Y[t-30min].
    """
    result = df
    observed = _observed(result, value_column, as_of)
    week = observed.rolling(pd.Timedelta(days=7), closed="left", min_periods=7 * SLOTS_PER_DAY)
    result["rolling_mean_7d"] = week.mean()
    result["rolling_std_7d"] = week.std(ddof=1)
    result["rolling_q95_30d"] = observed.rolling(
        pd.Timedelta(days=30), closed="left", min_periods=30 * SLOTS_PER_DAY).quantile(.95)
    result["ramp_rate"] = observed.shift(1) - observed.shift(2)  # Variation des deux derniers créneaux connus.

    return result


@_prepare_frame
def create_sites_features(
    df: pd.DataFrame, value_column="total_energie_injectee_wh", sites_column="nb_points_injection",
    *, as_of=None, epsilon=1e-9, _q95=None,
) -> pd.DataFrame:
    """Group E. Past site counts and growth proxies; no current target-time counts.

    n_sites_solar is the previous half-hour's count, without forward filling.
    Site growth = (N[t-30min] - N[t-30min-delay]) / N[t-30min-delay].
    growth_yoy_q95 is a ratio (not ratio minus one) of two complete 30-day
    production windows ending at t and t-365d, both excluding their right edge.
    Units of epsilon match value_column. A zero site reference gives NaN.
    """
    check_real(epsilon, "epsilon", positive=True)
    result = df
    production = _observed(result, value_column, as_of)
    sites = _observed(result, sites_column, as_of, integer=True).shift(1)  # Comptage précédent, jamais celui de t.
    result["n_sites_solar"] = sites

    for days, name in ((30, "n_sites_growth_30d"), (365, "n_sites_growth_yoy")):
        past = _lag(sites, days)
        result[name] = _ratio(sites.to_numpy() - past, past)

    high = (_q95 if _q95 is not None else
            production.rolling(pd.Timedelta(days=30), closed="left", min_periods=30 * SLOTS_PER_DAY).quantile(.95))
    result["growth_yoy_q95"] = _ratio(high.to_numpy(), _lag(high, 365) + epsilon)

    return result


@_prepare_frame
def create_decomposition_features(
    df: pd.DataFrame, value_column="total_energie_injectee_wh", *, as_of=None,
    period: int = 48, history_days: int = 30, refit_every="1D",
) -> pd.DataFrame:
    """Group F. Causal STL snapshots, fitted on complete past windows only.

    Refit daily at UTC midnight by default; period=48 captures the UTC daily
    cycle. Reuse each snapshot until the next refit. Never decompose the full
    series and shift its fitted components: that would include future data.

    Extrapolate the last fitted trend with its 30-day OLS slope (units/day),
    repeat the last fitted seasonal cycle, and compute the previous observed
    residual against those components. Missing fit windows leave all F values
    missing. No interpolation. as_of caps every snapshot's historical cutoff.
    """
    check_integer(period, "period", minimum=2)
    check_integer(history_days, "history_days", minimum=30)
    if history_days * SLOTS_PER_DAY < 2 * period:
        raise ValueError("L'historique STL doit couvrir au moins deux périodes complètes.")

    try:
        interval = pd.Timedelta(refit_every)
    except (ValueError, TypeError) as error:
        raise ValueError("refit_every doit être une durée fixe positive.") from error

    if pd.isna(interval) or interval <= pd.Timedelta(0) or interval % HALF_HOUR:
        raise ValueError("refit_every doit être un multiple positif de 30 minutes.")

    from statsmodels.tsa.seasonal import STL

    result = df
    production = _observed(result, value_column, as_of)
    limit = _cutoff(as_of)
    anchors = result.index.floor(interval)
    if limit is not None:
        anchors = anchors.where(anchors <= limit, limit)

    features = np.full((len(result), 4), np.nan)  # Colonnes : tendance, saison, résidu retardé, pente.
    window = pd.Timedelta(days=int(history_days))
    slope_steps = 30 * SLOTS_PER_DAY
    x = np.arange(slope_steps, dtype=float) / SLOTS_PER_DAY
    centered = x - x.mean()

    for origin in anchors.unique():
        left = result.index.searchsorted(origin - window)
        right = result.index.searchsorted(origin)
        past = production.iloc[left:right].to_numpy(dtype=float)  # Fenêtre [origin - window, origin[.
        if len(past) != history_days * SLOTS_PER_DAY or not np.isfinite(past).all():
            continue

        fitted = STL(past, period=int(period), robust=True).fit()
        trend = fitted.trend[-slope_steps:]
        slope = np.dot(centered, trend - trend.mean()) / np.dot(centered, centered)
        positions = np.flatnonzero(anchors == origin)
        times = result.index[positions]
        steps = np.asarray((times - (origin - HALF_HOUR)) / HALF_HOUR, dtype=np.int64)
        cycle = fitted.seasonal[-period:]
        projected = fitted.trend[-1] + slope * steps / SLOTS_PER_DAY
        seasonal = cycle[(steps - 1) % period]  # Répéter le dernier cycle saisonnier connu.
        previous = production.reindex(times - HALF_HOUR).to_numpy(dtype=float)
        previous_trend = fitted.trend[-1] + slope * (steps - 1) / SLOTS_PER_DAY
        residual = previous - previous_trend - cycle[(steps - 2) % period]
        features[positions] = np.column_stack([projected, seasonal, residual, np.full(len(times), slope)])

    result[list(PRODUCTION_FEATURE_GROUPS["F"])] = features

    return result


def build_production_features(
    df: pd.DataFrame, groups: Iterable[str] = tuple(PRODUCTION_FEATURE_GROUPS), *,
    latitude=None, longitude=None, timezone="Europe/Paris", value_column="total_energie_injectee_wh",
    sites_column="nb_points_injection", as_of=None, lag_basis="utc",
    decomposition_period=48, decomposition_history_days=30, decomposition_refit_every="1D",
) -> pd.DataFrame:
    """Build selected groups A–F; return features only on a regular UTC index.

    Input is a single filtered regional solar F5/P0 series, with timezone-aware
    horodate (or DatetimeIndex). Historical groups use strictly earlier slots:
    without as_of this is rolling one-step information, not a fixed-origin
    multi-step forecast. For the latter pass as_of and include target timestamps
    in df; unknowable observations stay missing. Calendar/astronomy remain known.

    Individual create_* helpers retain input columns for chaining. This builder
    removes targets, raw counts and arbitrary extras to avoid accidental leakage.
    No feature selection, training, imputation or future prediction is performed.
    """
    selected = check_collection(groups, "groups", choices=PRODUCTION_FEATURE_GROUPS)
    _cutoff(as_of)

    result = _production_frame(df)
    # __wrapped__ appelle le calcul seul : la grille est déjà préparée ici.
    if "A" in selected:
        result = create_calendar_features.__wrapped__(result, timezone=timezone)

    if "B" in selected:
        result = create_astro_features.__wrapped__(result, latitude, longitude, timezone=timezone)

    if "C" in selected:
        result = create_lag_features.__wrapped__(result, value_column, basis=lag_basis, timezone=timezone, as_of=as_of)

    if "D" in selected:
        result = create_rolling_features.__wrapped__(result, value_column, as_of=as_of)

    if "E" in selected:
        result = create_sites_features.__wrapped__(result, value_column, sites_column, as_of=as_of,
                                                   _q95=result["rolling_q95_30d"] if "D" in selected else None)

    if "F" in selected:
        result = create_decomposition_features.__wrapped__(
            result, value_column, as_of=as_of, period=decomposition_period,
            history_days=decomposition_history_days, refit_every=decomposition_refit_every)


    columns = [column for group in selected for column in PRODUCTION_FEATURE_GROUPS[group]]

    return result[columns].copy()
