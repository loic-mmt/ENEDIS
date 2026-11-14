#!/usr/bin/env python3
"""Préparer une base filtrée et des masques communs, sans imputer ni modifier raw/."""

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from enedis.prediction.imputation_evaluation import prepare_evaluation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="53", help="Code région sur deux chiffres ; défaut Bretagne.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/imputed")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gaps-per-split", type=int, default=100)
    parser.add_argument("--timezone", default="Europe/Paris")
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--split-starts", nargs=3, metavar=("VALIDATION", "CALIBRATION", "TEST"),
                        help="Débuts des trois phases en YYYY-MM ; sinon déduits de la période source.")
    args = parser.parse_args(argv)
    try:
        print(f"Préparation de l'évaluation — région {args.region}…", flush=True)
        directory = prepare_evaluation(args.data_dir, args.output_dir, args.region, seed=args.seed,
                                       gaps_per_split=args.gaps_per_split, timezone=args.timezone,
                                       split_starts=args.split_starts, batch_size=args.batch_size)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        snapshot = (directory / manifest["base_relative_path"]).resolve()
        base = pd.read_parquet(snapshot / "observations.parquet")
        cases = pd.read_parquet(directory / "gaps.parquet")
        masks = pd.read_parquet(directory / "masks.parquet")
        print(f"Base : {len(base):,} lignes ; mémoire pandas {base.memory_usage(deep=True).sum()/1e6:.2f} Mo.")
        print(f"Trous naturels : {manifest['n_natural_gaps']} séquences, {manifest['n_natural_missing']} créneaux.")
        for split, period in manifest["periods"].items():
            selected = cases.loc[cases["split"].eq(split)]
            points = int(masks["split"].eq(split).sum())
            print(f"{split:<12} {period['start']} → {period['end_exclusive']} (fin exclue) ; "
                  f"{len(selected)} trous, {points} valeurs masquées.")
        print("Durées artificielles (créneaux de 30 min) :", cases["n_slots"].value_counts().sort_index().to_dict())
        print("Changements de saison faute de candidat :", int((~cases["season_matched"]).sum()))
        print("Comptages de sites masqués pour reproduire le profil source :", int(masks["mask_sites"].sum()))
        print(f"Expérience : {directory}")
        print("Même source et mêmes paramètres : réutilisation des fichiers vérifiés, sans réécriture.")
        print("Aucune imputation effectuée. raw/ inchangé. Charger les entrées via load_evaluation_split.")
    except (OSError, ValueError, KeyError) as error:
        print(f"Échec de la préparation : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
