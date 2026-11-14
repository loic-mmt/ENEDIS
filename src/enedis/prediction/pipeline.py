from typing import Literal

import numpy as np
import pandas as pd

from .baselines import linear_baseline, persistance_baseline
from .contracts import PredictionRequest, validate_history
from .utils import check_choice, check_integer


def run_baseline(
    history: pd.DataFrame,
    predictionRequest: PredictionRequest,
    baseline_type: Literal["persistance", "linear"],
    info_length: int = 3,
) -> pd.DataFrame:
    """Forecast each commune using the canonical annual history contract.

    The request defines the target, cutoff year and horizon. Future rows are
    excluded before calculation. One output row is returned per commune and
    forecast year; unavailable forecasts remain NaN, including communes with
    no history before the cutoff. The input is never modified. Results are
    neither cached nor saved: callers may reuse this DataFrame across models.
    """
    if not isinstance(predictionRequest, PredictionRequest):
        raise TypeError("predictionRequest doit être une PredictionRequest.")
    check_choice(baseline_type, ("persistance", "linear"), "baseline_type")
    if baseline_type == "linear":
        check_integer(info_length, "info_length", minimum=2)
    validate_history(history)

    # Une seule source pour la date de départ : la demande de prévision.
    origin = predictionRequest.origin_year
    horizon = predictionRequest.horizon
    target = predictionRequest.target
    prediction_years = range(origin + 1, origin + horizon + 1)  # Première prévision : origin + 1.
    rows = []

    # Chaque baseline reçoit uniquement l'historique passé d'une commune.
    for commune, commune_history in history.groupby("code_commune", sort=False, observed=True):
        past = commune_history.loc[commune_history["annee"] <= origin]
        if past.empty:
            predictions = np.full(horizon, np.nan)  # Commune conservée, prévisions indisponibles.
        elif baseline_type == "persistance":
            predictions = persistance_baseline(past, target, "annee", origin, horizon)
        else:
            predictions = linear_baseline(past, target, "annee", origin, horizon, info_length)

        # Même format de sortie pour toutes les communes et les baselines.
        rows.extend({
            "code_commune": commune,
            "target": target,
            "origin_year": origin,
            "prediction_year": year,
            "prediction": prediction,
            "model": baseline_type,
        } for year, prediction in zip(prediction_years, predictions, strict=True))

    return pd.DataFrame(rows, columns=[
        "code_commune", "target", "origin_year", "prediction_year", "prediction", "model",
    ])
