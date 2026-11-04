#!/usr/bin/env python3
"""Comparer interpolation, J−1 et médiane saisonnière sur les mêmes trous masqués."""

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from enedis.prediction.imputation_baselines import METHODS, run_references
from enedis.prediction.imputation_evaluation import prepare_evaluation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="53")
    parser.add_argument("--evaluation-dir", type=Path, help="Expérience déjà préparée ; sinon retrouver/créer celle par défaut.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/imputed")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gaps-per-split", type=int, default=100)
    parser.add_argument("--split", choices=["validation", "calibration", "test"], default="validation")
    parser.add_argument("--methods", choices=METHODS, nargs="+", default=list(METHODS))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--min-observations", type=int, default=3)
    parser.add_argument("--day-basis", choices=["local", "utc"], default="local")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    args = parser.parse_args(argv)
    try:
        evaluation = args.evaluation_dir or prepare_evaluation(
            args.data_dir, args.output_dir, args.region, seed=args.seed, gaps_per_split=args.gaps_per_split)
        print(f"Références — phase {args.split}, jours {args.day_basis}…", flush=True)
        directory = run_references(evaluation, split=args.split, methods=args.methods, days=args.days,
                                    min_observations=args.min_observations, day_basis=args.day_basis,
                                    latitude=args.latitude, longitude=args.longitude)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        print(f"{manifest['n_gaps']} trous ; {manifest['n_targets']} observations cachées.")
        print("Erreurs pondérées selon les durées naturelles, exprimées en MWh par demi-heure.")
        print("Interpolation : deux bords connus ; J−1/médiane : observations antérieures au début du trou.")
        scores = pd.read_parquet(directory / "scores.parquet")
        selected = scores.loc[scores["stratum"].isin(["overall", "light"])]
        columns = ["method", "scope", "stratum_value", "n_total", "n_predicted", "coverage",
                   "mae_mwh", "rmse_mwh", "bias_mwh"]
        print(selected[columns].to_string(index=False, na_rep="—", float_format=lambda value: f"{value:.4f}"))
        if args.latitude is None:
            print("Scores solaires jour/nuit non calculés : fournir --latitude et --longitude.")
        else:
            print(f"Point utilisé pour jour/nuit : {args.latitude}, {args.longitude}.")
        print(f"Résultats : {directory}")
        print("Prédictions séparées de la vérité ; base et raw/ inchangés.")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Échec des références : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
