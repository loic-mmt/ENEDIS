"""Diagnostiquer les cellules vides sans modifier les données sources."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv"
OUTPUT = ROOT / "data/processed/rapports"
CATEGORY = ["CODE CATEGORIE CONSOMMATION", "CODE GRAND SECTEUR"]


def merge(previous, current):
    return current if previous is None else previous.add(current, fill_value=0)


def grouped_counts(empty, values, keys):
    flags = empty.add_prefix("vide:")
    for key in keys:
        flags[key] = values[key]
    groups = flags.groupby(keys, dropna=False)
    result = groups.sum()
    result["nombre_lignes"] = groups.size()
    return result


def detailed_report(counts):
    counts = counts.astype("int64").reset_index()
    keys = [c for c in counts.columns if not c.startswith("vide:")]
    report = counts.melt(id_vars=keys, var_name="colonne", value_name="nombre_vides")
    report["colonne"] = report["colonne"].str.removeprefix("vide:")
    report["pourcentage_vides"] = (
        report["nombre_vides"] / report["nombre_lignes"] * 100
    ).round(2)
    return report


def main(source=SOURCE, output=OUTPUT, chunksize=100_000):
    output.mkdir(parents=True, exist_ok=True)
    total = 0
    missing = by_year = by_category = combinations = None
    print(f"Analyse de {source}", flush=True)
    for chunk in pd.read_csv(
        source, dtype="string", keep_default_na=False,
        chunksize=chunksize, encoding="utf-8-sig",
    ):
        values = chunk.apply(lambda column: column.str.strip())
        empty = values.eq("")
        missing = merge(missing, empty.sum())
        by_year = merge(by_year, grouped_counts(empty, values, ["Année"]))
        by_category = merge(by_category, grouped_counts(empty, values, CATEGORY))

        # Ce statut décrit le champ ; il ne démontre pas la cause d'un manque.
        raw = values["Nombre de mailles secretisées"]
        number = pd.to_numeric(raw, errors="coerce")
        status = pd.Series("non_numerique", index=chunk.index, dtype="string")
        status.loc[number.eq(0)] = "zero"
        status.loc[number.gt(0)] = "positive"
        status.loc[number.lt(0)] = "negative_a_verifier"
        status.loc[raw.eq("")] = "vide"
        patterns = values[["Année", *CATEGORY]].copy()
        patterns["conso_totale_vide"] = empty["Conso totale (MWh)"]
        patterns["nb_sites_vide"] = empty["nb_sites"]
        patterns["conso_moyenne_vide"] = empty["Conso moyenne (MWh)"]
        patterns["statut_mailles_secretisees"] = status
        counts = patterns.groupby(list(patterns.columns), dropna=False).size()
        combinations = merge(combinations, counts)
        total += len(chunk)
        print(f"{total:,} lignes analysées…", flush=True)
    if not total:
        raise ValueError("Le fichier ne contient aucune observation.")
    report = pd.DataFrame({
        "colonne": missing.index,
        "nombre_lignes": total,
        "nombre_vides": missing.to_numpy(),
        "pourcentage_vides": (missing.to_numpy() / total * 100).round(2),
    })
    patterns_report = combinations.astype("int64").rename("nombre_lignes").reset_index()
    denominators = patterns_report.groupby(
        ["Année", *CATEGORY], dropna=False
    )["nombre_lignes"].transform("sum")
    patterns_report["pourcentage_du_groupe"] = (
        patterns_report["nombre_lignes"] / denominators * 100
    ).round(2)
    reports = {
        "consommation_valeurs_manquantes.csv": report,
        "consommation_manques_par_annee.csv": detailed_report(by_year),
        "consommation_manques_par_categorie_secteur.csv": detailed_report(by_category),
        "consommation_combinaisons_manques.csv": patterns_report,
    }
    for name, frame in reports.items():
        destination = output / name
        frame.to_csv(destination, index=False)
        print(f"Rapport enregistré dans : {destination}", flush=True)


if __name__ == "__main__":
    main()
