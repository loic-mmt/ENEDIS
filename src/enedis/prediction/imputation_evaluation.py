"""Reusable filtered snapshots and common masked blocks for imputation experiments.

No imputation is performed here. Raw Parquet files are only read. Each snapshot
contains one regional solar F5/P0 series, not the full production dataset.
"""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from .utils import (check_choice, check_column, check_datetime_index, check_finite, check_integer, check_numeric)

ENERGY = "total_energie_injectee_wh"
SITES = "nb_points_injection"
STEP = pd.Timedelta(minutes=30)
SPLITS = ("validation", "calibration", "test")
VERSION = 1


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_bundle(destination, tables, metadata):
    """Publish a new directory atomically; never overwrite an existing experiment."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Dossier déjà présent : {destination}")

    with TemporaryDirectory(prefix=".preparation-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        hashes = {}

        for name, table in tables.items():
            if Path(name).suffix == ".csv":
                table.to_csv(staging / name, index=False)
            else:
                table.to_parquet(staging / name, index=True, compression="zstd")

            hashes[name] = _file_digest(staging / name)

        (staging / "manifest.json").write_text(
            json.dumps({**metadata, "files": hashes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staging.rename(destination)  # Publier seulement une fois tous les fichiers écrits.


def _read_manifest(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION:
        raise ValueError("Version de préparation non prise en charge ; créer une nouvelle expérience.")

    for name, expected in manifest["files"].items():
        if Path(name).name != name or _file_digest(directory / name) != expected:
            raise ValueError(f"Fichier absent ou modifié dans l'expérience : {name}")

    return manifest


def read_solar_series(files, region, batch_size=100_000):
    """Arrow pushes the region/F5/P0 filter and reads just three useful columns."""
    dataset = ds.dataset([str(path) for path in files], format="parquet", partitioning="hive")
    selection = ((ds.field("code_region") == region)
                 & (ds.field("filiere_de_production") == "F5 : Solaire")
                 & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances"))
    columns = ["horodate", ENERGY, SITES]
    parts = [batch.to_pandas() for batch in dataset.scanner(
        columns=columns, filter=selection, batch_size=batch_size, use_threads=False,
        batch_readahead=1, fragment_readahead=1).to_batches() if len(batch)]
    if not parts:
        raise ValueError(f"Aucune production solaire F5/P0 pour la région {region}.")

    frame = pd.concat(parts, ignore_index=True)
    dates = pd.DatetimeIndex(pd.to_datetime(frame.pop("horodate"), utc=True, errors="raise"))
    check_datetime_index(dates, step="30min")
    frame.index = dates.rename("horodate")
    frame = frame.sort_index()

    for column in (ENERGY, SITES):
        check_numeric(frame[column], column, minimum=0, integer=column == SITES)
        frame[column] = frame[column].to_numpy(dtype=float, na_value=np.nan)

    frame["source_present"] = True
    grid = pd.date_range(frame.index[0], frame.index[-1], freq="30min", name="horodate")
    frame = frame.reindex(grid)  # Conserver les demi-heures absentes comme trous.
    frame["source_present"] = frame["source_present"].fillna(False).astype(bool)
    frame["is_observed"] = frame[ENERGY].notna()

    return frame


def _season(month):
    return ("winter", "spring", "summer", "autumn")[(month % 12) // 3]


def natural_gaps(base, timezone="Europe/Paris"):
    missing = ~base["is_observed"].to_numpy(dtype=bool)
    transitions = np.diff(np.r_[False, missing, False].astype(int))
    # Bornes [début, fin[ des trous.
    starts, ends = np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1)
    rows = []

    for number, (left, right) in enumerate(zip(starts, ends)):
        local = base.index[left].tz_convert(timezone)
        rows.append({"template_id": number, "start": base.index[left],
                     "end_exclusive": base.index[right - 1] + STEP, "n_slots": int(right - left),
                     "season": _season(local.month), "hour_slot": int(local.hour * 2 + local.minute // 30),
                     "sites_missing": base.iloc[left:right][SITES].isna().tolist()})

    if not rows:
        raise ValueError("Aucun trou naturel : impossible de déduire le profil des masques de cette série.")

    return pd.DataFrame(rows)


def evaluation_periods(index, timezone="Europe/Paris", split_starts=None):
    """Default: first third context, second third validation, then calibration/test."""
    local = index.tz_convert(timezone)
    months = pd.period_range(local[0].strftime("%Y-%m"), local[-1].strftime("%Y-%m"), freq="M")
    if split_starts is None:
        if len(months) < 6:
            raise ValueError("Au moins six mois requis, ou fournir les trois mois de début des splits.")

        context = len(months) // 3
        validation = len(months) // 3
        calibration = max(1, len(months) // 6)
        split_starts = [str(months[position]) for position in
                        (context, context + validation, context + validation + calibration)]
    if len(split_starts) != 3:
        raise ValueError("Trois débuts attendus : validation, calibration, test (YYYY-MM).")

    dates = [pd.Period(value, freq="M").start_time.tz_localize(timezone).tz_convert("UTC") for value in split_starts]
    boundaries = [index[0], *dates, index[-1] + STEP]
    if any(left >= right for left, right in zip(boundaries, boundaries[1:])):
        raise ValueError("Les splits doivent être ordonnés et laisser une période de contexte initial.")

    return {name: {"start": left.isoformat(), "end_exclusive": right.isoformat()}
            for name, left, right in zip(("context", *SPLITS), boundaries, boundaries[1:])}


def sample_masks(base, templates, periods, gaps_per_split=100, seed=42, timezone="Europe/Paris"):
    """Nonoverlapping complete observed blocks, matching real lengths and local hours.

    Include each real gap length once per split when the budget allows, then
    sample natural templates empirically. Prefer the same season; record any
    seasonal fallback. Reserve a known neighbor on either side for interpolation.
    """
    rng = np.random.default_rng(seed)
    index = base.index
    local = index.tz_convert(timezone)
    seasons = np.array([_season(month) for month in local.month])
    hour_slots = np.asarray(local.hour * 2 + local.minute // 30)
    known = base["is_observed"].to_numpy(dtype=bool)
    prefix = np.r_[0, np.cumsum(known)]  # Comptage d'observations par intervalle en O(1).
    reserved = np.zeros(len(base), dtype=bool)
    lengths = templates["n_slots"].unique().tolist()
    natural_probabilities = templates["n_slots"].value_counts(normalize=True).to_dict()
    cases, points = [], []

    for split in SPLITS:
        begin = index.searchsorted(pd.Timestamp(periods[split]["start"]))
        end = index.searchsorted(pd.Timestamp(periods[split]["end_exclusive"]))
        pools = {}

        def candidates(length, hour):
            key = (length, hour)
            if key not in pools:
                positions = np.arange(max(1, begin), min(end - length, len(base) - length))
                # Bloc + deux voisins connus.
                enough = prefix[positions + length + 1] - prefix[positions - 1] == length + 2
                pools[key] = positions[enough & (hour_slots[positions] == hour)]

            return pools[key]

        ordered_lengths = rng.permutation(lengths).tolist()

        for number in range(gaps_per_split):
            length = ordered_lengths[number] if number < len(ordered_lengths) else None
            choices = templates if length is None else templates.loc[templates["n_slots"].eq(length)]
            chosen = None

            # Retry other templates if nearby sampled blocks used the available candidates.
            for template_index in rng.permutation(choices.index):
                template = templates.loc[template_index]
                count, hour = int(template["n_slots"]), int(template["hour_slot"])
                positions = candidates(count, hour)
                preferred = positions[seasons[positions] == template["season"]]
                fallback = positions[seasons[positions] != template["season"]]

                for position in np.r_[rng.permutation(preferred), rng.permutation(fallback)]:
                    if not reserved[position - 1:position + count + 1].any():
                        chosen = (int(position), template)
                        break

                if chosen is not None:
                    break

            if chosen is None:
                raise ValueError(f"Pas assez de blocs connus pour {gaps_per_split} trous dans {split} ; réduire le nombre.")

            position, template = chosen
            count = int(template["n_slots"])
            reserved[position - 1:position + count + 1] = True
            gap_id = f"{split}_{number:04d}"
            cases.append({"gap_id": gap_id, "split": split, "start": index[position],
                          "end_exclusive": index[position + count], "n_slots": count,
                          "template_id": int(template["template_id"]), "season": seasons[position],
                          "hour_slot": int(hour_slots[position]),
                          "season_matched": bool(seasons[position] == template["season"]),
                          "reconstruction_as_of": pd.Timestamp(periods[split]["end_exclusive"])})
            sites_pattern = template["sites_missing"]

            for offset in range(count):
                points.append({"horodate": index[position + offset], "gap_id": gap_id, "split": split,
                               "n_slots": count, "mask_sites": bool(sites_pattern[offset])})

    cases = pd.DataFrame(cases)
    # Rare lengths are deliberately represented: preserve weights for later aggregate scores.
    cases["duration_weight"] = 0.

    for split in SPLITS:
        selected = cases["split"].eq(split)
        frequencies = cases.loc[selected, "n_slots"].value_counts(normalize=True)
        cases.loc[selected, "duration_weight"] = cases.loc[selected, "n_slots"].map(
            lambda length: natural_probabilities[length] / frequencies[length])

    masks = pd.DataFrame(points).set_index("horodate").sort_index()
    weights = cases.set_index("gap_id")["duration_weight"]
    masks["duration_weight"] = masks["gap_id"].map(weights)

    return cases, masks


def prepare_evaluation(raw_dir, output_dir, region="53", *, seed=42, gaps_per_split=100,
                       timezone="Europe/Paris", split_starts=None, batch_size=100_000):
    """Persist one filtered snapshot and small reusable masks/truth per experiment."""
    raw_dir, output_dir = Path(raw_dir).resolve(), Path(output_dir).resolve()
    if output_dir.is_relative_to(raw_dir) or raw_dir.is_relative_to(output_dir):
        raise ValueError("Le dossier de sortie doit être séparé de data/raw, sans chevauchement.")
    if not isinstance(region, str) or len(region) != 2 or not region.isascii() or not region.isdigit():
        raise ValueError("Code région attendu sur deux chiffres.")
    check_integer(seed, "seed", minimum=0, strict=True)
    check_integer(gaps_per_split, "gaps_per_split", minimum=1, strict=True)
    check_integer(batch_size, "batch_size", minimum=1, strict=True)
    files = sorted((raw_dir / "production_regionale").rglob("*.parquet"))
    if not files:
        raise ValueError("Aucun Parquet dans le dossier de production régionale.")

    source = {"version": VERSION, "region": region, "timezone": timezone, "filiere": "F5", "puissance": "P0",
              "files": [{"path": str(file.relative_to(raw_dir)), "bytes": file.stat().st_size,
                         "mtime_ns": file.stat().st_mtime_ns} for file in files]}
    root = output_dir / "production_regionale" / f"region_{region}"
    snapshot = root / "bases" / _digest(source)
    if snapshot.resolve().is_relative_to(raw_dir):
        raise ValueError("Le chemin de la base redirige vers data/raw.")
    if snapshot.exists():
        base_manifest = _read_manifest(snapshot)
        base = pd.read_parquet(snapshot / "observations.parquet")
        templates = pd.read_parquet(snapshot / "natural_gaps.parquet")
    else:
        base = read_solar_series(files, region, batch_size)
        templates = natural_gaps(base, timezone)
        _write_bundle(snapshot, {"observations.parquet": base, "natural_gaps.parquet": templates},
                      {"version": VERSION, "source": source, "rows": len(base), "unit": "Wh"})
        base_manifest = _read_manifest(snapshot)

    periods = evaluation_periods(base.index, timezone, split_starts)
    config = {"version": VERSION, "snapshot": snapshot.name, "seed": seed, "gaps_per_split": gaps_per_split,
              "timezone": timezone, "periods": periods, "protocol": "retrospective_reconstruction",
              "sampling": "empirical_templates_with_rare_lengths_and_possible_season_fallback"}
    evaluation = root / "evaluations" / _digest(config)
    if evaluation.resolve().is_relative_to(raw_dir):
        raise ValueError("Le chemin de l'expérience redirige vers data/raw.")
    if evaluation.exists():
        _read_manifest(evaluation)

        return evaluation

    cases, masks = sample_masks(base, templates, periods, gaps_per_split, seed, timezone)
    truth = masks.copy()
    truth["true_value_wh"] = base[ENERGY].reindex(truth.index)
    truth["true_sites"] = base[SITES].reindex(truth.index)
    _write_bundle(evaluation, {"gaps.parquet": cases, "masks.parquet": masks, "truth.parquet": truth},
                  {**config, "base_relative_path": f"../../bases/{snapshot.name}",
                   "base_sha256": base_manifest["files"]["observations.parquet"],
                   "n_natural_gaps": len(templates), "n_natural_missing": int((~base["is_observed"]).sum())})

    return evaluation


def load_evaluation_split(evaluation_dir, split):
    """Return masked inputs, separate truth and gap metadata for one phase.

    ALL artificial targets are hidden before features are computed. Inputs stop
    at this phase's end to keep calibration/test periods out of earlier phases.
    Forward-only methods must further restrict context to each gap's start;
    backward methods may use later observations strictly before the phase cutoff.
    Never pass truth or the immutable base directly as model input.
    """
    check_choice(split, SPLITS, "split")
    evaluation_dir = Path(evaluation_dir).resolve()
    manifest = _read_manifest(evaluation_dir)
    snapshot = (evaluation_dir / manifest["base_relative_path"]).resolve()
    if snapshot.parent != evaluation_dir.parent.parent / "bases":
        raise ValueError("La base doit se trouver dans le dossier bases de la même région.")

    base_manifest = _read_manifest(snapshot)
    if base_manifest["files"]["observations.parquet"] != manifest["base_sha256"]:
        raise ValueError("La base ne correspond plus à cette expérience.")

    frame = pd.read_parquet(snapshot / "observations.parquet")
    masks = pd.read_parquet(evaluation_dir / "masks.parquet")
    frame.loc[masks.index, ENERGY] = np.nan  # Masquer tous les splits avant de construire les features.
    frame.loc[masks.index, "is_observed"] = False
    frame.loc[masks.index[masks["mask_sites"]], SITES] = np.nan
    cutoff = pd.Timestamp(manifest["periods"][split]["end_exclusive"])
    frame = frame.loc[frame.index < cutoff].copy()
    truth = pd.read_parquet(evaluation_dir / "truth.parquet")
    cases = pd.read_parquet(evaluation_dir / "gaps.parquet")

    return frame, truth.loc[truth["split"].eq(split)].copy(), cases.loc[cases["split"].eq(split)].copy()


def score_reconstruction(truth, predictions, *, weight_column=None):
    """Same observed targets for every method; report coverage and errors in MWh.

    Missing predictions reduce coverage. Compare accuracy on common successfully
    predicted points as well when methods have different coverage. Group truth
    by split, duration, season or daylight before calling for stratified scores.
    Set weight_column='duration_weight' for naturally weighted aggregate errors;
    coverage still reports the raw point fraction, alongside weighted_coverage.
    """
    if not isinstance(predictions, pd.Series):
        raise ValueError("Prédictions attendues comme Series avec DatetimeIndex.")
    check_datetime_index(predictions.index, "Dates des prédictions")
    check_datetime_index(truth.index, "Dates de la vérité", nonempty=True)
    actual = truth["true_value_wh"].to_numpy(dtype=float)
    check_finite(actual, "Vérité d'évaluation")
    predicted = predictions.reindex(truth.index).to_numpy(dtype=float, na_value=np.nan)
    valid = np.isfinite(predicted)  # Une prédiction absente réduit la couverture.
    errors = (predicted[valid] - actual[valid]) / 1e6  # Wh -> MWh ; positif = surestimation.
    if weight_column is None:
        weights = np.ones(len(truth))
    else:
        check_column(truth, weight_column, "Colonne de pondération")
        weights = truth[weight_column].to_numpy(dtype=float)
        if not np.isfinite(weights).all() or (weights <= 0).any():
            raise ValueError("Poids strictement positifs et finis requis.")

    return {"n_total": len(truth), "n_predicted": int(valid.sum()), "coverage": float(valid.mean()),
            "weighted_coverage": float(weights[valid].sum() / weights.sum()),
            "mae_mwh": float(np.average(np.abs(errors), weights=weights[valid])) if len(errors) else np.nan,
            "rmse_mwh": float(np.sqrt(np.average(np.square(errors), weights=weights[valid]))) if len(errors) else np.nan,
            "bias_mwh": float(np.average(errors, weights=weights[valid])) if len(errors) else np.nan}
