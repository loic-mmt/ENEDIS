#!/usr/bin/env python3
"""Validation Kumo en marche avant : A+B+C par défaut, prédictions bornées à zéro."""

import argparse
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from enedis.prediction.imputation_baselines import compare_references
from enedis.prediction.imputation_evaluation import (
    VERSION, _digest, _file_digest, _read_manifest, _write_bundle,
    load_evaluation_split, prepare_evaluation,
)
from enedis.prediction.imputation_models import FEATURE_GROUPS, reconstruct_with_model
from enedis.prediction.models import KumoTabularRegressor
from enedis.prediction.utils import check_collection, check_integer, check_real


RUN_VERSION = 2


def _arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", type=Path, help="Expérience existante ; sinon préparer/retrouver celle par défaut.")
    parser.add_argument("--region", default="53", help="Code région utilisé lors de la préparation ; défaut Bretagne.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/imputed")
    parser.add_argument("--seed", type=int, default=42, help="Graine des masques ; ignorée avec --evaluation-dir.")
    parser.add_argument("--gaps-per-split", type=int, default=100, help="Nombre de trous préparés par phase.")
    parser.add_argument("--latitude", type=float, required=True, help="Latitude du point représentatif de la région.")
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--context-size", type=int, default=2048, help="Maximum d'observations connues par fit.")
    parser.add_argument("--min-observations", type=int, default=2)
    parser.add_argument("--groups", choices=FEATURE_GROUPS, nargs="+", default=list(FEATURE_GROUPS),
                        help="Groupes de features ; défaut A B C. Utiliser A B pour comparer sans lags.")
    parser.add_argument("--size", choices=("small", "medium", "large"), default="large", help="Taille du modèle Kumo.")
    parser.add_argument("--num-estimators", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=256, help="Taille des lots de prédiction Kumo.")
    parser.add_argument("--device", default="auto", help="auto, cpu ou cuda[:numéro].")
    parser.add_argument("--model-seed", type=int, default=42, help="Graine Kumo, indépendante des masques.")
    parser.add_argument("--max-gaps", type=int, help="Essai sur les N premiers trous ; tous les masques restent appliqués.")

    return parser.parse_args(argv)


def _check_parameters(args):
    args.groups = check_collection(args.groups, "groups", choices=FEATURE_GROUPS)
    for name in ("gaps_per_split", "num_estimators", "batch_size"):
        check_integer(getattr(args, name), name, minimum=1)
    check_integer(args.context_size, "context_size", minimum=2)
    check_integer(args.min_observations, "min_observations", minimum=2, maximum=args.context_size)
    check_integer(args.seed, "seed", minimum=0)
    check_integer(args.model_seed, "model_seed", minimum=0)
    if args.max_gaps is not None:
        check_integer(args.max_gaps, "max_gaps", minimum=1)
    check_real(args.latitude, "latitude", minimum=-90, maximum=90)
    check_real(args.longitude, "longitude", minimum=-180, maximum=180)


def _versions():
    packages = ("numpy", "pandas", "pyarrow", "pvlib", "scikit-learn", "torch", "structured-data-models")
    versions = {}
    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None

    return versions


def _run(args):
    evaluation = args.evaluation_dir or prepare_evaluation(
        args.data_dir, args.output_dir, args.region, seed=args.seed, gaps_per_split=args.gaps_per_split,
    )
    evaluation = Path(evaluation).resolve()
    manifest = _read_manifest(evaluation)
    inputs, truth, gaps = load_evaluation_split(evaluation, "validation")
    total_gaps = len(gaps)

    # Limiter les cibles évaluées, sans révéler les autres observations masquées.
    gaps = gaps.sort_values("start", kind="stable").head(args.max_gaps or total_gaps).copy()
    truth = truth.loc[truth["gap_id"].isin(gaps["gap_id"])].copy()
    model_options = {"size": args.size, "device": args.device, "num_estimators": args.num_estimators,
                     "batch_size": args.batch_size, "random_state": args.model_seed, "context_size": None}
    source_files = [Path(__file__).resolve(), *[
        ROOT / "src/enedis/prediction" / f"{name}.py" for name in (
            "imputation_models", "imputation_evaluation", "imputation_baselines", "features", "models", "utils",
        )
    ]]
    config = {
        "version": VERSION, "run_version": RUN_VERSION, "evaluation_id": evaluation.name,
        "evaluation_sha256": _file_digest(evaluation / "manifest.json"),
        "split": "validation", "direction": "forward", "groups": args.groups, "unit": "Wh",
        "lag_basis": "utc", "prediction_clip_min": 0.,
        "timezone": manifest["timezone"], "latitude": args.latitude, "longitude": args.longitude,
        "context_size": args.context_size, "min_observations": args.min_observations,
        "model": "KumoTabularRegressor", "model_options": model_options,
        "gap_ids": gaps["gap_id"].tolist(), "packages": _versions(),
        "source_sha256": {str(path.relative_to(ROOT)): _file_digest(path) for path in source_files},
    }
    run_name = "kumo_forward_" + "".join(args.groups).lower()
    destination = evaluation.parent.parent / "runs" / evaluation.name / run_name / _digest(config)
    resolved = destination.resolve()
    if "raw" in resolved.parts or resolved.is_relative_to(args.data_dir.resolve()):
        raise ValueError("Les résultats doivent rester hors des données raw/.")

    if destination.exists():
        _read_manifest(destination)  # Cache réutilisé seulement si ses fichiers sont intacts.
        print("Résultat existant vérifié : aucun nouveau fit.", flush=True)
        return destination

    print(f"Validation forward {'+'.join(args.groups)} : {len(gaps)}/{total_gaps} trous, "
          f"{len(truth)} demi-heures masquées ; clipping à zéro.", flush=True)
    print(f"Kumo {args.size}, {args.num_estimators} estimateurs, contexte maximal {args.context_size}.", flush=True)
    print("Premier fit : téléchargement des poids si nécessaire ; exécution locale.", flush=True)
    completed = 0

    def progress(info):
        nonlocal completed
        completed += 1
        print(f"[{completed}/{len(gaps)}] {info['gap_id']} : {info['status']} ; "
              f"{info['n_context']} observations ; fit {info['fit_seconds']:.2f} s, "
              f"prédiction {info['predict_seconds']:.2f} s ; {info['n_clipped']} valeurs bornées à zéro", flush=True)

    model = KumoTabularRegressor(**model_options)
    started = perf_counter()
    predictions, diagnostics = reconstruct_with_model(
        inputs, gaps, model, latitude=args.latitude, longitude=args.longitude,
        timezone=manifest["timezone"], context_size=args.context_size,
        min_observations=args.min_observations, groups=args.groups, on_gap_end=progress,
    )
    # Même calcul des scores pondérés et des strates que pour les références simples.
    scores = compare_references(truth, {"kumo": predictions}, timezone=manifest["timezone"],
                                latitude=args.latitude, longitude=args.longitude, information={"kumo": "past_only"})
    _write_bundle(destination, {
        "predictions.parquet": predictions, "diagnostics.parquet": diagnostics, "scores.parquet": scores,
        "scores_global.csv": scores.loc[scores["stratum"].eq("overall")].copy(),
        "scores_stratified.csv": scores.loc[~scores["stratum"].eq("overall")].copy(),
    }, {**config, "evaluation_relative_path": f"../../../../evaluations/{evaluation.name}",
        "n_gaps": len(gaps), "n_validation_gaps": total_gaps, "n_targets": len(truth),
        "elapsed_seconds": perf_counter() - started, "device_used": str(getattr(model, "device_", args.device))})

    return destination


def _print_report(directory):
    manifest = _read_manifest(directory)
    diagnostics = pd.read_parquet(directory / "diagnostics.parquet")
    scores = pd.read_parquet(directory / "scores.parquet")
    selected = scores.loc[scores["scope"].eq("all_targets") & scores["stratum"].isin(["overall", "light"])]
    columns = ["stratum", "stratum_value", "n_total", "n_predicted", "coverage", "weighted_coverage",
               "mae_mwh", "rmse_mwh", "bias_mwh"]
    print("\nScores pondérés par les durées naturelles ; erreurs en MWh par demi-heure.")
    print(selected[columns].to_string(index=False, na_rep="—", float_format=lambda value: f"{value:.4f}"))
    print(f"Clipping : {int(diagnostics['n_clipped'].sum())} prédictions négatives ramenées à zéro.")
    if manifest["n_gaps"] < manifest["n_validation_gaps"]:
        print("Essai limité : scores sur un sous-ensemble, pondérations de l'expérience conservées.")
    print(f"Point utilisé : {manifest['latitude']}, {manifest['longitude']}.")
    print(f"Résultats : {directory}")
    print("Prédictions et diagnostics exportés ; vrais trous non remplis, raw/ et expérience inchangés.")


def main(argv=None):
    args = _arguments(argv)
    try:
        _check_parameters(args)
        directory = _run(args)
        _print_report(directory)
    except (OSError, ValueError, KeyError, TypeError, ImportError, RuntimeError) as error:
        print(f"Échec du test forward {'+'.join(args.groups)} : {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
