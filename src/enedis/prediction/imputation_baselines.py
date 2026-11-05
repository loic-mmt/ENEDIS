"""Simple gap-reconstruction references, separate from annual forecast baselines."""

from pathlib import Path

import numpy as np
import pandas as pd

from .imputation_evaluation import (
    ENERGY, STEP, VERSION, _digest, _file_digest, _read_manifest, _write_bundle,
    load_evaluation_split, score_reconstruction,
)
from .utils import (
    check_choice, check_collection, check_integer, check_real, check_reconstruction_inputs,
)


METHODS = ("linear", "previous_day", "seasonal_median")
INFORMATION = {"linear": "two_sided", "previous_day": "past_only", "seasonal_median": "past_only"}
REFERENCE_VERSION = 1


def _day_keys(target, days, basis, timezone):
    if basis == "utc":
        return target - pd.Timedelta(days=days)

    wall = target.tz_convert(timezone).tz_localize(None) - pd.DateOffset(days=days)

    return wall.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")


def reconstruct_reference(observed, gaps, method, *, days=7, min_observations=3,
                          day_basis="local", timezone="Europe/Paris"):
    """Predict whole hidden blocks without reading truth or updating context.

    linear: exact two known border slots, elapsed-time interpolation, no extrapolation.
    previous_day: previous civil day/same local hour by default, no fallback.
    seasonal_median: median at that same hour over the previous `days` dates,
    requiring `min_observations` values. Explicit zeros are observations.

    Past-only methods use observations strictly before each block's START;
    predictions within a block never become observations for subsequent targets.
    Local historical hours without a unique DST mapping give NaN. All values
    and returned predictions use the input unit (Wh in the evaluation runner).
    """
    check_choice(method, METHODS, "method")
    check_choice(day_basis, ("local", "utc"), "day_basis")
    check_integer(days, "days", minimum=1)
    check_integer(min_observations, "min_observations", minimum=1, maximum=days)
    # Validate the timezone even if this particular series does not cross DST.
    pd.Timestamp("2024-01-01", tz="UTC").tz_convert(timezone)
    series, blocks = check_reconstruction_inputs(observed, gaps)
    parts = []

    for gap_id, start, end, target in blocks:
        if method == "linear":
            borders = series.reindex(pd.DatetimeIndex([start - STEP, end]))
            support = np.full(len(target), int(borders.notna().sum()))
            if borders.notna().all():
                fractions = np.arange(1, len(target) + 1) / (len(target) + 1)  # Poids entre les deux bornes connues.
                predicted = borders.iloc[0] + fractions * (borders.iloc[1] - borders.iloc[0])
            else:
                predicted = np.full(len(target), np.nan)

            # Earliest issuance whose strictly earlier slots include the right border.
            cutoff = end + STEP
        else:
            references = []

            for offset in range(1, (1 if method == "previous_day" else int(days)) + 1):
                keys = _day_keys(target, offset, day_basis, timezone)
                values = series.reindex(keys).to_numpy(dtype=float)
                references.append(np.where(keys < start, values, np.nan))  # Aucun appui à l'intérieur du trou.

            # Lignes = cibles ; colonnes = jours passés.
            history = pd.DataFrame(np.column_stack(references), index=target)
            support = history.notna().sum(axis=1).to_numpy(dtype=int)
            required = 1 if method == "previous_day" else int(min_observations)
            predicted = history.median(axis=1).where(support >= required).to_numpy(dtype=float)
            cutoff = start  # Toutes les prédictions du bloc partagent le même passé.
        parts.append(pd.DataFrame({"gap_id": gap_id, "method": method, "prediction_wh": predicted,
                                   "n_support": support, "information": INFORMATION[method],
                                   "information_cutoff": cutoff}, index=target))

    return pd.concat(parts).sort_index()


def _empty_score():
    return {"n_total": 0, "n_predicted": 0, "coverage": np.nan, "weighted_coverage": np.nan,
            "mae_mwh": np.nan, "rmse_mwh": np.nan, "bias_mwh": np.nan}


def compare_references(truth, predictions, *, timezone="Europe/Paris", latitude=None, longitude=None,
                       information=None):
    """Weighted and unweighted errors, including the common successful targets.

    Day/night is optional and requires an explicit representative point. It uses
    geometric solar elevation at the source timestamp, not an arbitrary clock
    band. Hour/season/length strata remain available without coordinates.
    information optionally maps other model names to 'past_only'/'two_sided'.
    """
    if not predictions:
        raise ValueError("Au moins une référence est nécessaire.")
    information = {**INFORMATION, **(information or {})}
    for method in predictions:
        check_choice(information.get(method), ("past_only", "two_sided"), f"information[{method}]")

    common = np.ones(len(truth), dtype=bool)

    for prediction in predictions.values():
        common &= np.isfinite(prediction["prediction_wh"].reindex(truth.index).to_numpy(dtype=float))

    local = truth.index.tz_convert(timezone)
    season_names = np.array([("winter", "spring", "summer", "autumn")[(month % 12) // 3] for month in local.month])
    strata = [("overall", "all", np.ones(len(truth), dtype=bool))]

    for length in sorted(truth["n_slots"].unique()):
        strata.append(("duration", str(length), truth["n_slots"].eq(length).to_numpy()))

    for hour in sorted(set(local.hour)):
        strata.append(("hour", str(hour), np.asarray(local.hour == hour)))

    for season in sorted(set(season_names)):
        strata.append(("season", season, season_names == season))

    if (latitude is None) != (longitude is None):
        raise ValueError("Fournir latitude et longitude ensemble pour les scores jour/nuit.")
    if latitude is not None:
        for name, value, bound in (("latitude", latitude, 90), ("longitude", longitude, 180)):
            check_real(value, name, minimum=-bound, maximum=bound)

        from pvlib.solarposition import get_solarposition
        daylight = get_solarposition(truth.index, latitude, longitude)["elevation"].gt(0).to_numpy()
        strata.extend([("light", "day", daylight), ("light", "night", ~daylight)])

    rows = []

    for method, prediction in predictions.items():
        values = prediction["prediction_wh"]

        for scope, scope_mask in (("all_targets", np.ones(len(truth), dtype=bool)), ("common_targets", common)):
            for stratum, value, mask in strata:
                subset = truth.loc[scope_mask & mask]
                weighted = score_reconstruction(subset, values, weight_column="duration_weight") if len(subset) else _empty_score()
                plain = score_reconstruction(subset, values) if len(subset) else _empty_score()
                rows.append({"method": method, "information": information[method], "scope": scope,
                             "stratum": stratum, "stratum_value": value, **weighted,
                             "mae_unweighted_mwh": plain["mae_mwh"],
                             "rmse_unweighted_mwh": plain["rmse_mwh"]})

    return pd.DataFrame(rows)


def run_references(evaluation_dir, *, split="validation", methods=METHODS, days=7,
                   min_observations=3, day_basis="local", latitude=None, longitude=None):
    """Persist separate prediction patches and common scores; never alter the base.

    Default execution evaluates validation only. Calibration and test must be
    requested explicitly after method/hyperparameter choices are fixed.
    """
    evaluation_dir = Path(evaluation_dir).resolve()
    manifest = _read_manifest(evaluation_dir)
    methods = tuple(check_collection(methods, "methods", choices=METHODS))
    inputs, truth, gaps = load_evaluation_split(evaluation_dir, split)
    config = {"version": VERSION, "reference_version": REFERENCE_VERSION, "evaluation_id": evaluation_dir.name,
              "evaluation_sha256": _file_digest(evaluation_dir / "manifest.json"), "split": split,
              "methods": list(methods), "days": days, "min_observations": min_observations,
              "day_basis": day_basis, "timezone": manifest["timezone"],
              "latitude": latitude, "longitude": longitude, "unit": "Wh"}
    destination = evaluation_dir.parent.parent / "runs" / evaluation_dir.name / "references" / _digest(config)
    # Prepared evaluations live outside raw. Also reject accidentally copied trees there.
    if "raw" in destination.resolve().parts:
        raise ValueError("Les résultats doivent rester hors de raw/.")
    if destination.exists():
        _read_manifest(destination)

        return destination

    observed = inputs[ENERGY].where(inputs["is_observed"])
    predictions = {method: reconstruct_reference(observed, gaps, method, days=days,
                                                  min_observations=min_observations, day_basis=day_basis,
                                                  timezone=manifest["timezone"]) for method in methods}
    scores = compare_references(truth, predictions, timezone=manifest["timezone"],
                                latitude=latitude, longitude=longitude)
    overall = scores.loc[scores["stratum"].eq("overall")].copy()
    tables = {f"predictions_{method}.parquet": frame for method, frame in predictions.items()}
    tables.update({"scores.parquet": scores, "scores_global.csv": overall,
                   "scores_stratified.csv": scores.loc[~scores["stratum"].eq("overall")].copy()})
    _write_bundle(destination, tables, {**config, "evaluation_relative_path":
                                      f"../../../../evaluations/{evaluation_dir.name}",
                                      "n_gaps": len(gaps), "n_targets": len(truth),
                                      "daylight_definition": "solar_elevation_at_timestamp > 0" if latitude is not None else None})

    return destination
