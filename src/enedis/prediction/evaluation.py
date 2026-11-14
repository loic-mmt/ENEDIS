from collections.abc import Iterable, Sequence
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from .contracts import PredictionRequest
from .pipeline import run_baseline
from .utils import check_collection, check_integer


def align_predictions(history: pd.DataFrame, predictions: pd.DataFrame, target: str) -> pd.DataFrame:
    """Align one model/origin's forecasts with actuals from validated history.

    Keep unavailable observations as missing. Signed error is prediction - actual:
    positive means overprediction. No forecasts are recalculated here.
    """
    actuals = history[["code_commune", "annee", target]].rename(columns={
        "annee": "prediction_year", target: "actual",
    })
    pairs = predictions.merge(actuals, on=["code_commune", "prediction_year"], how="left", validate="one_to_one")
    pairs["horizon"] = pairs["prediction_year"] - pairs["origin_year"]
    pairs["error"] = pairs["prediction"] - pairs["actual"]  # Positif = surestimation.
    pairs["available"] = pairs[["actual", "prediction"]].notna().all(axis=1)
    pairs["evaluated"] = pairs["available"]

    return pairs


def _metrics(valid: pd.DataFrame) -> dict[str, float]:
    """Missing evaluation data produces missing scores, never perfect scores."""
    if valid.empty:
        return {"mae": np.nan, "rmse": np.nan, "bias": np.nan}

    y_true = valid["actual"].to_numpy(dtype=float)
    y_pred = valid["prediction"].to_numpy(dtype=float)

    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
        "bias": float(np.mean(y_pred - y_true)),
    }


def evaluate_baseline(
    history: pd.DataFrame,
    predictionRequest: PredictionRequest,
    baseline_type: Literal["persistance", "linear"],
    info_length: int = 3,
) -> dict[str, float | int]:
    """Score one baseline/origin, pooling the requested horizons for one target.

    Missing actuals or forecasts are excluded. Use backtest_baselines to compare
    several models/origins on common observations, with scores by horizon.
    """
    predictions = run_baseline(history, predictionRequest, baseline_type, info_length)
    pairs = align_predictions(history, predictions, predictionRequest.target)
    valid = pairs.loc[pairs["evaluated"]]
    if valid.empty:
        raise ValueError("Aucune paire prévision/observation disponible pour l'évaluation.")

    scores = _metrics(valid)

    return {"mae": scores["mae"], "rmse": scores["rmse"], "n_predictions": len(pairs), "n_evaluated": len(valid)}


def backtest_baselines(
    history: pd.DataFrame,
    target: str,
    origin_years: Iterable[int],
    horizon: int,
    baseline_types: Sequence[Literal["persistance", "linear"]] = ("persistance", "linear"),
    info_length: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (detailed forecasts, scores by model and horizon) for one target.

    Run each baseline once per origin. History contains training observations
    and held-out actuals; run_baseline excludes future rows from prediction.
    Both models are scored on the same commune/origin/year pairs. `available`
    describes each model's own valid pairs; `evaluated` marks the common subset.
    Scores pool origins, with one equal weight per evaluated forecast. Bias and
    detailed error are prediction - actual. Coverage is the fraction evaluated,
    not the coverage of a prediction interval. Groups with no evaluable pairs
    keep NaN scores and zero coverage. Nothing is saved or cached automatically.
    """
    origins = check_collection(origin_years, "origin_years", integers=True, strict=True)
    methods = check_collection(baseline_types, "baseline_types", choices=("persistance", "linear"))
    if "linear" in methods:
        check_integer(info_length, "info_length", minimum=2)

    requests = [PredictionRequest(target, origin, horizon) for origin in origins]

    # Une exécution par couple année de départ / baseline.
    frames = []

    for request in requests:
        for method in methods:
            predictions = run_baseline(history, request, method, info_length)
            pairs = align_predictions(history, predictions, target)
            pairs["info_length"] = info_length if method == "linear" else pd.NA
            frames.append(pairs)

    details = pd.concat(frames, ignore_index=True)
    details["info_length"] = details["info_length"].astype("Int64")  # Entiers avec valeurs manquantes.

    # Comparer sur les mêmes observations ; conserver toutes les lignes en détail.
    keys = ["code_commune", "target", "origin_year", "prediction_year"]
    # Connues pour tous les modèles.
    details["evaluated"] = details.groupby(keys, sort=False)["available"].transform("all")

    rows = []

    for (model, step), group in details.groupby(["model", "horizon"], sort=False):
        valid = group.loc[group["evaluated"]]
        rows.append({
            "target": target, "model": model, "horizon": int(step),
            **_metrics(valid),
            "n_predictions": len(group), "n_available": int(group["available"].sum()),
            "n_evaluated": len(valid), "coverage": len(valid) / len(group),
        })

    return details, pd.DataFrame(rows)


def RMSE(
    history: pd.DataFrame,
    predictionRequest: PredictionRequest,
    baseline_type: Literal["persistance", "linear"],
    info_length: int = 3,
) -> float:
    """Return RMSE; use evaluate_baseline to obtain both scores in one run."""
    return evaluate_baseline(history, predictionRequest, baseline_type, info_length)["rmse"]


def MAE(
    history: pd.DataFrame,
    predictionRequest: PredictionRequest,
    baseline_type: Literal["persistance", "linear"],
    info_length: int = 3,
) -> float:
    """Return MAE; use evaluate_baseline to obtain both scores in one run."""
    return evaluate_baseline(history, predictionRequest, baseline_type, info_length)["mae"]
