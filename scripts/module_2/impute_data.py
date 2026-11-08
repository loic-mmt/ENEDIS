#!/usr/bin/env python3
"""Validation Kumo/SARIMA/SARIMAX en marche avant, prédictions bornées à zéro."""

import argparse
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from enedis.prediction.progress import TerminalProgress, quiet_model_output

# Module léger : l'animation est disponible avant les imports scientifiques.
with TerminalProgress() as startup, quiet_model_output():
    if __name__ == "__main__":
        startup.print_status("Imports des bibliothèques…")
    import pandas as pd
    from joblib import Parallel, delayed

    from enedis.prediction.imputation_baselines import compare_references
    from enedis.prediction.imputation_evaluation import (
        VERSION, _digest, _file_digest, _read_manifest, _write_bundle,
        load_evaluation_split, prepare_evaluation,
    )
    from enedis.prediction.imputation_models import FEATURE_GROUPS, prepare_model_features, reconstruct_with_model
    from enedis.prediction.models import KumoTabularRegressor
    from enedis.prediction.sarima import SARIMARegressor, SARIMAXRegressor
    from enedis.prediction.utils import check_collection, check_integer, check_real


RUN_VERSION = 5


def _arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("kumo", "sarima", "sarimax"), default="kumo")

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

    parser.add_argument("--order", nargs=3, type=int, default=[1, 0, 1], metavar=("p", "d", "q"))
    parser.add_argument("--seasonal-order", nargs=4, type=int, default=[1, 1, 1, 48], metavar=("P", "D", "Q", "s"))
    parser.add_argument("--maxiter", type=int, default=100, help="Itérations maximales de SARIMA/SARIMAX.")
    parser.add_argument("--workers", type=int, default=1, help="Processus CPU pour les fits SARIMA/SARIMAX indépendants.")

    return parser.parse_args(argv)


def _check_parameters(args):
    args.groups = check_collection(args.groups, "groups", choices=FEATURE_GROUPS)

    for name in ("gaps_per_split", "num_estimators", "batch_size"):
        check_integer(getattr(args, name), name, minimum=1)

    check_integer(args.context_size, "context_size", minimum=2)
    check_integer(args.min_observations, "min_observations", minimum=2, maximum=args.context_size)
    check_integer(args.seed, "seed", minimum=0)
    check_integer(args.model_seed, "model_seed", minimum=0)
    check_integer(args.workers, "workers", minimum=1)
    check_integer(args.maxiter, "maxiter", minimum=1)

    if args.model == "kumo" and args.workers != 1:
        raise ValueError("--workers concerne SARIMA/SARIMAX ; Kumo réutilise son instance en série.")
    if args.max_gaps is not None:
        check_integer(args.max_gaps, "max_gaps", minimum=1)

    check_real(args.latitude, "latitude", minimum=-90, maximum=90)
    check_real(args.longitude, "longitude", minimum=-180, maximum=180)


def _versions():
    packages = ("numpy", "pandas", "pyarrow", "pvlib", "scikit-learn", "torch", "structured-data-models", "statsmodels")
    versions = {}

    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None

    return versions


def _sarima_gap(inputs, gap, model_class, model_options, reconstruction_options):
    with quiet_model_output():
        return reconstruct_with_model(inputs, gap, model_class(**model_options), **reconstruction_options)


def _run(args, display):
    display.print_status("Préparation de l'expérience…")
    evaluation = args.evaluation_dir or prepare_evaluation(
        args.data_dir, args.output_dir, args.region, seed=args.seed, gaps_per_split=args.gaps_per_split,
    )
    evaluation = Path(evaluation).resolve()

    display.print_status("Chargement des données de validation…")
    manifest = _read_manifest(evaluation)
    inputs, truth, gaps = load_evaluation_split(evaluation, "validation")
    total_gaps = len(gaps)

    # Limiter les cibles évaluées, sans révéler les autres observations masquées.
    gaps = gaps.sort_values("start", kind="stable").head(args.max_gaps or total_gaps).copy()
    truth = truth.loc[truth["gap_id"].isin(gaps["gap_id"])].copy()

    model_options = {"size": args.size, "device": args.device, "num_estimators": args.num_estimators,
                     "batch_size": args.batch_size, "random_state": args.model_seed, "context_size": None}
    groups = args.groups
    model_class = KumoTabularRegressor

    if args.model in ("sarima", "sarimax"):
        if args.model == "sarima":
            groups = []  # SARIMAX conserve les groupes demandés ; SARIMA ignore les features.

        model_options = {"order": tuple(args.order), "seasonal_order": tuple(args.seasonal_order),
                         "trend": "n", "maxiter": args.maxiter}
        model_class = SARIMARegressor if args.model == "sarima" else SARIMAXRegressor

    source_files = [Path(__file__).resolve(), *[
        ROOT / "src/enedis/prediction" / f"{name}.py" for name in (
            "imputation_models", "imputation_evaluation", "imputation_baselines", "data", "features", "models", "utils", "sarima", "progress",
        )
    ]]

    display.print_status("Vérification du cache…")
    config = {
        "version": VERSION, "run_version": RUN_VERSION, "evaluation_id": evaluation.name,
        "evaluation_sha256": _file_digest(evaluation / "manifest.json"),
        "split": "validation", "direction": "forward", "groups": groups, "unit": "Wh",
        "lag_basis": "utc", "prediction_clip_min": 0.,
        "timezone": manifest["timezone"], "latitude": args.latitude, "longitude": args.longitude,
        "context_size": args.context_size, "min_observations": args.min_observations,
        "model": args.model, "model_options": model_options, "workers": args.workers,
        "gap_ids": gaps["gap_id"].tolist(), "packages": _versions(),
        "source_sha256": {str(path.relative_to(ROOT)): _file_digest(path) for path in source_files},
    }

    run_name = f"{args.model}_forward"
    if groups:
        run_name += "_" + "".join(groups).lower()

    destination = evaluation.parent.parent / "runs" / evaluation.name / run_name / _digest(config)
    resolved = destination.resolve()
    if "raw" in resolved.parts or resolved.is_relative_to(args.data_dir.resolve()):
        raise ValueError("Les résultats doivent rester hors des données raw/.")

    if destination.exists():
        _read_manifest(destination)  # Cache réutilisé seulement si ses fichiers sont intacts.
        display.write("Résultat existant vérifié : aucun nouveau fit.")
        return destination

    completed = 0

    def progress(info):
        nonlocal completed
        completed += 1
        display.iteration(completed, len(gaps), info["model"], info["fit_seconds"], info["predict_seconds"])

    started = perf_counter()
    features = None
    if groups:
        display.print_status(f"Feature engineering : {'+'.join(groups)}…")
        features = prepare_model_features(inputs, gaps, latitude=args.latitude, longitude=args.longitude,
                                          timezone=manifest["timezone"], groups=groups)

    display.print_status("Préparation des modèles et des contextes…")
    options = {"latitude": args.latitude, "longitude": args.longitude, "timezone": manifest["timezone"],
               "context_size": args.context_size, "min_observations": args.min_observations,
               "groups": groups, "features": features, "quiet": True}

    if args.workers == 1:
        with quiet_model_output():
            model = model_class(**model_options)

        display.stop()  # Aucune animation pendant les lignes de fit/prédiction.
        predictions, diagnostics = reconstruct_with_model(inputs, gaps, model, **options, on_gap_end=progress)
        device_used = str(getattr(model, "device_", "cpu"))
    else:
        display.stop()
        tasks = (delayed(_sarima_gap)(inputs, gaps.iloc[[position]].copy(), model_class, model_options, options)
                 for position in range(len(gaps)))
        parts, details = [], []

        for prediction, diagnostic in Parallel(n_jobs=args.workers, return_as="generator_unordered", verbose=0)(tasks):
            parts.append(prediction)
            details.append(diagnostic)
            progress(diagnostic.iloc[0].to_dict())

        predictions = pd.concat(parts).sort_index()
        diagnostics = pd.concat(details, ignore_index=True).sort_values("start", kind="stable").reset_index(drop=True)
        device_used = "cpu"

    # Même calcul des scores pondérés et des strates que pour les références simples.
    display.print_status("Calcul des scores…")
    scores = compare_references(truth, {args.model: predictions}, timezone=manifest["timezone"],
                                latitude=args.latitude, longitude=args.longitude, information={args.model: "past_only"})

    display.print_status("Export des résultats…")
    _write_bundle(destination, {
        "predictions.parquet": predictions, "diagnostics.parquet": diagnostics, "scores.parquet": scores,
        "scores_global.csv": scores.loc[scores["stratum"].eq("overall")].copy(),
        "scores_stratified.csv": scores.loc[~scores["stratum"].eq("overall")].copy(),
    }, {**config, "evaluation_relative_path": f"../../../../evaluations/{evaluation.name}",
        "n_gaps": len(gaps), "n_validation_gaps": total_gaps, "n_targets": len(truth),
        "elapsed_seconds": perf_counter() - started, "device_used": device_used})

    return destination


def _print_report(directory, display):
    manifest = _read_manifest(directory)
    diagnostics = pd.read_parquet(directory / "diagnostics.parquet")
    scores = pd.read_parquet(directory / "scores.parquet")

    selected = scores.loc[scores["scope"].eq("all_targets") & scores["stratum"].isin(["overall", "light"])]
    columns = ["stratum", "stratum_value", "n_total", "n_predicted", "coverage", "weighted_coverage",
               "mae_mwh", "rmse_mwh", "bias_mwh"]
    lines = ["\nScores pondérés par les durées naturelles ; erreurs en MWh par demi-heure.",
             selected[columns].to_string(index=False, na_rep="—", float_format=lambda value: f"{value:.4f}"),
             f"Clipping : {int(diagnostics['n_clipped'].sum())} prédictions négatives ramenées à zéro."]

    if "converged" in diagnostics and diagnostics.converged.eq(False).any():
        lines.append(f"Optimisations non convergées : {int(diagnostics.converged.eq(False).sum())} ; estimations conservées.")
    if manifest["n_gaps"] < manifest["n_validation_gaps"]:
        lines.append("Essai limité : scores sur un sous-ensemble, pondérations de l'expérience conservées.")

    lines.extend([f"Point utilisé : {manifest['latitude']}, {manifest['longitude']}.",
                  f"Résultats : {directory}",
                  "Prédictions et diagnostics exportés ; vrais trous non remplis, raw/ et expérience inchangés."])

    display.write("\n".join(lines))


def main(argv=None):
    args = _arguments(argv)

    with TerminalProgress() as display:
        try:
            _check_parameters(args)
            directory = _run(args, display)
            display.print_status("Préparation du rapport…")
            _print_report(directory, display)
        except (OSError, ValueError, KeyError, TypeError, ImportError, RuntimeError) as error:
            display.write(f"Échec du test forward {args.model} : {error}", error=True)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
