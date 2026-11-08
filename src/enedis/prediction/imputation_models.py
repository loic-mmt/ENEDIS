"""Forward reconstruction using calendar, solar and lagged production features."""

from contextlib import nullcontext
from time import perf_counter

import numpy as np
import pandas as pd

from .features import PRODUCTION_FEATURE_GROUPS, build_production_features
from .imputation_evaluation import ENERGY
from .models import KumoTabularRegressor, predict
from .progress import quiet_model_output
from .utils import (
    check_collection,
    check_dataframe,
    check_datetime_index,
    check_feature_columns,
    check_integer,
    check_real,
    check_reconstruction_inputs,
    check_timestamp,
)


FEATURE_GROUPS = ("A", "B", "C")


def _validation_inputs(inputs, gaps):
    check_dataframe(inputs, required=(ENERGY, "is_observed"), nonempty=True)
    check_datetime_index(inputs.index, nonempty=True, ordered=True, step="30min", regular=True)
    check_dataframe(gaps, required=("split", "reconstruction_as_of"), nonempty=True)
    check_collection(gaps["split"].unique(), "split", choices=("validation",))

    if (not pd.api.types.is_bool_dtype(inputs["is_observed"].dtype)
            or inputs["is_observed"].isna().any()):
        raise ValueError("is_observed doit contenir des booléens non manquants.")

    limits = [check_timestamp(value, "reconstruction_as_of", step="30min")
              for value in gaps["reconstruction_as_of"]]
    if len(set(limits)) != 1:
        raise ValueError("Les trous de validation doivent partager la même fin de phase.")

    # Écarter la calibration et le test, même si inputs les contient encore.
    cutoff = limits[0]
    frame = inputs.loc[inputs.index < cutoff]
    series, blocks = check_reconstruction_inputs(frame[ENERGY], gaps)
    observed = series.where(frame["is_observed"].to_numpy())
    blocks.sort(key=lambda block: block[1])

    return observed, blocks


def prepare_model_features(inputs, gaps, *, latitude, longitude, timezone="Europe/Paris", groups=FEATURE_GROUPS):
    """Compute reusable A/B/C features from fully masked, observed labels only."""
    observed, _ = _validation_inputs(inputs, gaps)
    groups = tuple(check_collection(groups, "groups", choices=FEATURE_GROUPS))
    frame = observed.to_frame(name=ENERGY) if "C" in groups else pd.DataFrame(index=observed.index)

    return build_production_features(frame, groups=groups, latitude=latitude, longitude=longitude,
                                     timezone=timezone, lag_basis="utc")


def reconstruct_with_model(
        inputs: pd.DataFrame,
        gaps: pd.DataFrame,
        model=None, *,
        latitude: float,
        longitude: float,
        timezone="Europe/Paris",
        context_size: int | None = 2048,
        min_observations: int = 2,
        groups=FEATURE_GROUPS,
        on_gap_end=None,
        features=None,
        quiet=False,
        ):
    """Return (predictions, diagnostics), validation only, forward, A+B+C by default.

    inputs/gaps come from load_evaluation_split(..., 'validation'). Energy is in
    Wh. Each block gets a fresh fit using observed labels strictly before its
    start; predictions never enter later contexts. A supplied model must expose
    fit(X, y) and predict(X), and is refitted in place. Default: local Kumo.

    A+B depend on dates; C looks back into observed, fully masked production.
    Features can be computed once without exposing labels inside any gap.
    Only selected feature columns reach the model. No file is read or written.
    Insufficient contexts produce NaN predictions and an explicit status. Other
    model errors propagate. Predictions are clipped at zero; raw values are kept.
    on_gap_end receives a copy of each completed block's diagnostics, if supplied.
    features may reuse prepare_model_features output for the same masked inputs.
    quiet silences model output; progress belongs to the caller, not to workers.
    """
    if context_size is not None:
        check_integer(context_size, "context_size", minimum=2)
    check_integer(min_observations, "min_observations", minimum=2)
    if on_gap_end is not None and not callable(on_gap_end):
        raise TypeError("on_gap_end doit être une fonction ou None.")

    if context_size is not None and context_size < min_observations:
        raise ValueError("context_size doit être supérieur ou égal à min_observations.")
    check_real(latitude, "latitude", minimum=-90, maximum=90)
    check_real(longitude, "longitude", minimum=-180, maximum=180)

    observed, blocks = _validation_inputs(inputs, gaps)

    if model is None:
        model = KumoTabularRegressor(context_size=None)

    if not callable(getattr(model, "fit", None)) or not callable(getattr(model, "predict", None)):
        raise TypeError("Le modèle doit fournir fit(X, y) et predict(X).")

    uses_features = getattr(model, "uses_features", True)
    groups = tuple(check_collection(groups, "groups", choices=FEATURE_GROUPS, allow_empty=not uses_features))

    # C utilise les observations masquées, jamais les prédictions réinjectées.
    if not uses_features:
        features = pd.DataFrame(index=observed.index)
    elif features is None:
        features = prepare_model_features(inputs, gaps, latitude=latitude, longitude=longitude,
                                          timezone=timezone, groups=groups)
    else:
        columns = [column for group in groups for column in PRODUCTION_FEATURE_GROUPS[group]]
        check_feature_columns(features, columns)
        if not features.index.equals(observed.index):
            raise ValueError("Les features préparées doivent couvrir la même grille que les entrées masquées.")
        features = features.loc[:, columns]

    known = observed.dropna()  # Zéros conservés ; valeurs non observées exclues.
    method = type(model).__name__
    parts, diagnostics = [], []

    for gap_id, start, end, target in blocks:
        past = known.loc[known.index < start]  # Même coupure pour tout le bloc.
        n_available = len(past)
        train = past if context_size is None else past.iloc[-context_size:]

        context_index = train.index[:0]  # Aucun contexte utilisé tant que fit n'a pas eu lieu.
        fit_seconds = predict_seconds = 0.

        raw_estimates = pd.Series(np.nan, index=target, name="prediction")
        estimates = raw_estimates.copy()
        n_clipped = 0
        status = "insufficient_context"

        if len(train) >= min_observations:
            train_features, train_target = features.loc[train.index].copy(), train.copy()

            with quiet_model_output() if quiet else nullcontext():
                timer = perf_counter()
                model.fit(train_features, train_target)
                fit_seconds = perf_counter() - timer

            context_index = getattr(model, "context_index_", train.index)

            query = target
            if getattr(model, "requires_future_features", False):
                # SARIMAX demande aussi les covariables des éventuels créneaux avant le trou.
                query = pd.date_range(
                    context_index[-1] + pd.Timedelta(minutes=30), end, freq="30min", inclusive="left",
                )

            query_features = features.loc[query].copy()

            with quiet_model_output() if quiet else nullcontext():
                timer = perf_counter()
                raw_estimates = predict(model, query_features)  # Tout le trou en un appel.
                predict_seconds = perf_counter() - timer

            raw_estimates = raw_estimates.loc[target]
            n_clipped = int(raw_estimates.lt(0).sum())
            estimates = raw_estimates.clip(lower=0)  # NaN conservés ; aucune borne supérieure.
            status = "ok" if estimates.notna().all() else "partial_prediction"

        parts.append(pd.DataFrame({
            "gap_id": gap_id, "method": method, "prediction_wh": estimates.to_numpy(),
            "prediction_raw_wh": raw_estimates.to_numpy(),
            "information": "past_only", "information_cutoff": start,
        }, index=target))

        diagnostics.append({
            "gap_id": gap_id, "model": method, "start": start, "end_exclusive": end, "n_slots": len(target),
            "n_available": n_available, "n_train": len(train), "n_context": len(context_index),
            "context_start": context_index[0] if len(context_index) else pd.NaT,
            "context_end": context_index[-1] if len(context_index) else pd.NaT,
            "fit_seconds": fit_seconds, "predict_seconds": predict_seconds, "status": status,
            "n_predicted": int(estimates.notna().sum()), "n_clipped": n_clipped, "groups": "+".join(groups),
            "converged": getattr(model, "converged_", None) if status != "insufficient_context" else None,
            "iterations": getattr(model, "iterations_", None) if status != "insufficient_context" else None,
            "n_time_steps": getattr(model, "n_time_steps_", len(train)),
        })

        if on_gap_end is not None:
            on_gap_end(diagnostics[-1].copy())  # L'affichage ne modifie pas les diagnostics.

    return pd.concat(parts).sort_index(), pd.DataFrame(diagnostics)
