#!/usr/bin/env python3
"""Analyser séparément les distributions : pv, consommation ou production.

Statistiques dans le terminal, tableaux CSV et graphiques PNG dans data/processed/rapports.
Lecture des fichiers bruts par lots ; aucune correction ni imputation des sources.
"""

import argparse
from collections import Counter
import math
import os
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd
import pyarrow.dataset as ds


ROOT = Path(__file__).resolve().parents[1]
COMMUNE_PATTERN = r"(?:[0-9]{5}|2[AB][0-9]{3})"
C_KEYS = ["commune", "category", "sector", "naf"]
QUANTILES = {"p01": .01, "p05": .05, "q25": .25, "mediane": .5,
             "q75": .75, "p95": .95, "p99": .99}


def department_from_code(codes):
    return codes.str[:2].where(~codes.str.startswith(("97", "98")), codes.str[:3])


def prepare_measures(frame, keys, factor=1.):
    """Marquer les exclusions d'analyse ; conserver leurs effectifs et les zéros."""
    frame = frame.copy()
    raw = frame.pop("raw_value")
    numbers = pd.to_numeric(raw, errors="coerce").astype(float)
    valid = np.isfinite(numbers) & numbers.ge(0)
    frame["missing"] = raw.isna() | raw.astype("string").str.strip().eq("").fillna(False)
    frame["invalid"] = ~valid & ~frame["missing"]
    # Vérification après concaténation : les répétitions peuvent traverser les lots/fichiers.
    frame["duplicate"] = frame.duplicated(keys, keep=False)
    frame["usable"] = valid & ~frame["duplicate"]
    frame["value"] = numbers.where(valid) * factor
    return frame


def read_consumption(path, region, start_year, end_year, chunksize):
    columns = ["Année", "Code Commune", "Code Département", "Code Région", "Nom Région",
               "CODE CATEGORIE CONSOMMATION", "CODE GRAND SECTEUR", "CODE SECTEUR NAF2",
               "Conso totale (MWh)"]
    parts, departments, names, diagnostics = [], set(), Counter(), Counter()
    for chunk in pd.read_csv(path, usecols=columns, dtype="string", keep_default_na=False,
                             encoding="utf-8-sig", chunksize=chunksize):
        diagnostics["lignes_parcourues"] += len(chunk)
        selected = chunk.loc[chunk["Code Région"].str.strip().str.zfill(2).eq(region)]
        diagnostics["lignes_region"] += len(selected)
        if selected.empty:
            continue
        names.update(selected["Nom Région"].str.strip().value_counts().to_dict())
        deps = selected["Code Département"].str.strip().str.zfill(2)
        departments.update(deps[deps.str.fullmatch(r"(?:[0-9]{2}|9[78][0-9]|2[AB])")])
        codes = selected["Code Commune"].str.strip()
        years = pd.to_numeric(selected["Année"].str.strip(), errors="coerce")
        key_valid = (codes.str.fullmatch(COMMUNE_PATTERN) & department_from_code(codes).eq(deps)
                     & years.between(1, 9999) & years.mod(1).eq(0))
        diagnostics["cles_rejetees"] += int((~key_valid).sum())
        eligible = key_valid & years.between(start_year, end_year)
        work = pd.DataFrame({
            "commune": codes[eligible], "year": years[eligible].astype(int),
            "category": selected.loc[eligible, "CODE CATEGORIE CONSOMMATION"].str.strip(),
            "sector": selected.loc[eligible, "CODE GRAND SECTEUR"].str.strip(),
            "naf": selected.loc[eligible, "CODE SECTEUR NAF2"].str.strip(),
            "raw_value": selected.loc[eligible, "Conso totale (MWh)"],
        })
        parts.append(work)
    if not departments:
        raise ValueError(f"Aucun département trouvé pour la région {region} dans la consommation.")
    columns = C_KEYS + ["year", "raw_value"]
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)
    name = next((name for name, _ in names.most_common() if name), region)
    return prepare_measures(frame, C_KEYS + ["year"]), departments, name, diagnostics


def read_pv(path, departments, start_year, end_year, chunksize):
    columns = ["date_mesure", "geocode_commune", "type_installation", "valeur"]
    parts, diagnostics = [], Counter()
    for chunk in pd.read_csv(path, usecols=columns, dtype="string", keep_default_na=False,
                             encoding="utf-8-sig", chunksize=chunksize):
        diagnostics["lignes_parcourues"] += len(chunk)
        solar = chunk.loc[chunk["type_installation"].str.strip().eq("Photovoltaïque")]
        codes = solar["geocode_commune"].str.strip()
        diagnostics["codes_invalides_toutes_regions"] += int((~codes.str.fullmatch(COMMUNE_PATTERN)).sum())
        selected = solar.loc[codes.str.fullmatch(COMMUNE_PATTERN)
                             & department_from_code(codes).isin(departments)]
        diagnostics["lignes_region"] += len(selected)
        dates = pd.to_datetime(selected["date_mesure"].str.strip(), errors="coerce", format="mixed")
        diagnostics["dates_rejetees"] += int(dates.isna().sum())
        years = dates.dt.year
        eligible = years.between(start_year, end_year)
        parts.append(pd.DataFrame({"commune": codes.loc[selected.index][eligible],
                                   "year": years[eligible].astype(int), "category": "PV",
                                   "raw_value": selected.loc[eligible, "valeur"]}))
    frame = (pd.concat(parts, ignore_index=True) if parts else
             pd.DataFrame(columns=["commune", "year", "category", "raw_value"]))
    return prepare_measures(frame, ["commune", "year"]), diagnostics


def common_sample(frame, unit_keys, years):
    valid = frame.loc[frame["usable"]]
    counts = valid.groupby(unit_keys)["year"].nunique()
    units = counts[counts.eq(len(years))].index.to_frame(index=False)
    return valid.merge(units, on=unit_keys, how="inner", validate="many_to_one")


def describe(frame):
    values = frame.loc[frame["usable"], "value"]
    summary = {
        "n_lignes": len(frame), "n_valides": len(values), "n_exclues": len(frame) - len(values),
        "n_manquantes": int(frame["missing"].sum()), "n_invalides": int(frame["invalid"].sum()),
        "n_lignes_repetees": int(frame["duplicate"].sum()), "n_zeros": int(values.eq(0).sum()),
        "minimum": values.min(), "moyenne": values.mean(), "ecart_type": values.std(ddof=1),
        "maximum": values.max(),
        "asymetrie": values.skew() if len(values) >= 3 and values.nunique() > 1 else np.nan,
    }
    summary.update({name: values.quantile(q) if len(values) else np.nan for name, q in QUANTILES.items()})
    summary["iqr"] = summary["q75"] - summary["q25"]
    if "commune" in frame:
        summary["n_communes_presentes"] = frame["commune"].nunique()
        summary["n_communes_valides"] = frame.loc[frame["usable"], "commune"].nunique()
    return summary


def annual_statistics(frame, years, unit_keys):
    common = common_sample(frame, unit_keys, years)
    rows = []
    for sample, data in (("disponible", frame), ("commun", common)):
        for category in sorted(frame["category"].unique()):
            for year in years:
                group = data.loc[data["year"].eq(year) & data["category"].eq(category)]
                rows.append({"echantillon": sample, "annee": year, "categorie": category, **describe(group)})
    return pd.DataFrame(rows)


def read_production(path, region, start_year, end_year, batch_size):
    files = sorted(Path(path).rglob("*.parquet"))
    if not files:
        raise ValueError(f"Aucun Parquet de production dans {path}.")
    dataset = ds.dataset([str(file) for file in files], format="parquet", partitioning="hive")
    selection = ((ds.field("code_region") == region)
                 & (ds.field("filiere_de_production") == "F5 : Solaire")
                 & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances"))
    parts, diagnostics = [], Counter()
    for batch in dataset.scanner(columns=["horodate", "total_energie_injectee_wh"],
                                 filter=selection, batch_size=batch_size).to_batches():
        source = batch.to_pandas()
        diagnostics["lignes_region_F5_P0"] += len(source)
        times = pd.to_datetime(source["horodate"], utc=True, errors="coerce", format="mixed")
        aligned = (times.notna() & times.dt.minute.mod(30).eq(0) & times.dt.second.eq(0)
                   & times.dt.microsecond.eq(0) & times.dt.nanosecond.eq(0))
        diagnostics["horodates_rejetees"] += int((~aligned).sum())
        local = times.dt.tz_convert("Europe/Paris")
        eligible = aligned.copy()
        if start_year is not None:
            eligible &= local.dt.year.ge(start_year)
        if end_year is not None:
            eligible &= local.dt.year.le(end_year)
        parts.append(pd.DataFrame({"instant": times[eligible],
                                   "mois": local[eligible].dt.strftime("%Y-%m"),
                                   "heure": local[eligible].dt.hour,
                                   "raw_value": source.loc[eligible, "total_energie_injectee_wh"]}))
    if not parts or not any(len(part) for part in parts):
        raise ValueError("Aucune observation solaire F5/P0 dans cette région et cette fenêtre.")
    frame = prepare_measures(pd.concat(parts, ignore_index=True), ["instant"], factor=1e-6)
    first = f"{start_year:04d}-01" if start_year is not None else frame["mois"].min()
    last = f"{end_year:04d}-12" if end_year is not None else frame["mois"].max()
    start = pd.Period(first, freq="M").start_time.tz_localize("Europe/Paris")
    end = (pd.Period(last, freq="M") + 1).start_time.tz_localize("Europe/Paris")
    # Le calendrier inclut les mois sans lignes et les journées de 23/25 heures.
    calendar = pd.date_range(start, end, freq="30min", inclusive="left")
    expected = pd.DataFrame({"mois": calendar.strftime("%Y-%m"), "heure": calendar.hour})
    return frame, expected, diagnostics


def production_statistics(frame, expected, keys):
    rows = []
    grouper = keys[0] if len(keys) == 1 else keys
    groups = {key: group for key, group in frame.groupby(grouper, sort=True)}
    for key, count in expected.groupby(grouper).size().items():
        group = groups.get(key, frame.iloc[:0])
        values = group.loc[group["usable"], "value"]
        row = describe(group)
        parts = key if isinstance(key, tuple) else (key,)
        row.update(zip(keys, parts))
        present = group["instant"].nunique()
        row.update({"n_attendues": int(count), "n_presentes": present,
                    "n_absentes": int(count) - present,
                    "couverture_pct": 100 * len(values) / count,
                    "complet": len(values) == count,
                    "somme_connue_mwh": values.sum(min_count=1),
                    "total_complet_mwh": values.sum() if len(values) == count else np.nan})
        rows.append(row)
    return pd.DataFrame(rows)


def extremes(frame, keys, count=5):
    parts = []
    for _, group in frame.loc[frame["usable"]].groupby(keys, sort=True):
        ordered = group.sort_values("value", kind="stable")
        parts.extend([ordered.head(count).assign(extreme="bas"), ordered.tail(count).assign(extreme="haut")])
    result = pd.concat(parts, ignore_index=True) if parts else frame.iloc[:0].assign(extreme="")
    return result.drop(columns=["missing", "invalid", "duplicate", "usable"], errors="ignore")


def pyplot(output):
    # Cache dans le dossier de sortie, fonctionnement sans interface graphique.
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def slug(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "vide"


def plot_histograms(groups, output, stem, title, unit, bins):
    """Bornes partagées entre facettes ; les zéros sont comptés hors axe logarithmique."""
    plt = pyplot(output)
    all_values = pd.concat([values for _, values in groups], ignore_index=True)
    for scale in ("lineaire", "log"):
        reference = all_values if scale == "lineaire" else all_values.loc[all_values.gt(0)]
        if reference.empty:
            continue
        if scale == "log":
            low, high = reference.min(), reference.max()
            if low == high:
                low, high = low / 2, high * 2
            edges = np.geomspace(low, high, bins + 1)
        else:
            edges = np.histogram_bin_edges(reference.to_numpy(), bins=bins)
        for page, offset in enumerate(range(0, len(groups), 16), start=1):
            selected = groups[offset:offset + 16]
            columns = min(4, len(selected))
            rows = math.ceil(len(selected) / columns)
            fig, axes = plt.subplots(rows, columns, figsize=(4 * columns, 2.9 * rows),
                                     squeeze=False, sharex=True)
            for axis, (label, values) in zip(axes.flat, selected):
                plotted = values if scale == "lineaire" else values.loc[values.gt(0)]
                axis.hist(plotted.to_numpy(), bins=edges, color="#287990", edgecolor="white", linewidth=.3)
                if scale == "log":
                    axis.set_xscale("log")
                axis.set_title(f"{label} | n={len(values)} ; zéros={int(values.eq(0).sum())}", fontsize=9)
                axis.set_xlabel(unit)
                axis.set_ylabel("Effectif")
                axis.grid(axis="y", alpha=.15)
            for axis in list(axes.flat)[len(selected):]:
                axis.set_visible(False)
            note = " | axe logarithmique : valeurs > 0 uniquement" if scale == "log" else ""
            fig.suptitle(f"{title} — {scale}{note}", fontsize=12)
            fig.tight_layout(rect=(0, 0, 1, .96))
            fig.savefig(output / f"{stem}_{scale}_{page:02d}.png", dpi=140)
            plt.close(fig)


def plot_annual_comparison(stats, output, category, title, unit):
    plt = pyplot(output)
    fig, (axis, counts) = plt.subplots(2, 1, figsize=(10, 6), sharex=True,
                                      gridspec_kw={"height_ratios": [3, 1]})
    for sample, color in (("disponible", "#287990"), ("commun", "#ba642b")):
        data = stats.loc[stats["categorie"].eq(category) & stats["echantillon"].eq(sample)]
        axis.plot(data["annee"], data["mediane"], "o-", color=color, label=f"{sample} : médiane")
        axis.fill_between(data["annee"], data["q25"], data["q75"], color=color, alpha=.15)
        counts.plot(data["annee"], data["n_valides"], "o-", color=color, label=sample)
    axis.set_ylabel(f"{unit} — médiane et Q25–Q75")
    axis.set_title(title)
    axis.legend()
    counts.set_ylabel("n valides")
    counts.set_xlabel("Année source")
    for ax in (axis, counts):
        ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(output / f"comparaison_{slug(category)}.png", dpi=140)
    plt.close(fig)


def plot_production_heatmaps(month_hour, output):
    plt = pyplot(output)
    for column, title, unit, bounds in [
        ("moyenne", "Énergie moyenne des demi-heures observées", "MWh / demi-heure", {}),
        ("couverture_pct", "Couverture des demi-heures attendues", "%", {"vmin": 0, "vmax": 100}),
    ]:
        table = month_hour.pivot(index="mois", columns="heure", values=column)
        fig, ax = plt.subplots(figsize=(11, max(4, len(table) * .25)))
        data = np.ma.masked_invalid(table.to_numpy(dtype=float))
        cmap = plt.get_cmap("viridis").copy()
        cmap.set_bad("#dddddd")
        visual = ax.imshow(data, aspect="auto", cmap=cmap, **bounds)
        ax.set_xticks(range(len(table.columns)), table.columns)
        ax.set_yticks(range(len(table.index)), table.index)
        ax.set_xlabel("Heure locale — Europe/Paris")
        ax.set_title(title)
        fig.colorbar(visual, ax=ax, label=unit)
        fig.tight_layout()
        fig.savefig(output / f"mois_heure_{column}.png", dpi=140)
        plt.close(fig)


def print_table(table, columns):
    print(table[columns].to_string(index=False, na_rep="—", float_format=lambda value: f"{value:.3f}"))


def analyse_annual(args, frame, name):
    if frame.empty:
        raise ValueError("Aucune observation dans cette région et cette fenêtre annuelle.")
    years = list(range(args.start_year, args.end_year + 1))
    unit_keys = ["commune"] if args.analysis == "pv" else C_KEYS
    stats = annual_statistics(frame, years, unit_keys)
    output = args.output_dir / f"region_{args.region}" / args.analysis / f"{args.start_year}-{args.end_year}"
    output.mkdir(parents=True, exist_ok=True)
    stats.to_csv(output / "statistiques_annuelles.csv", index=False)
    extremes(frame, ["year", "category"]).to_csv(output / "extremes.csv", index=False)
    unit = "MW" if args.analysis == "pv" else "MWh / ligne publiée"
    print(f"DISTRIBUTIONS {args.analysis.upper()} — {name} ({args.region}) — unité : {unit}")
    print("disponible : valeurs présentes valides, hors toutes les occurrences de clés répétées.")
    if args.analysis == "pv":
        print("commun : mêmes codes avec une valeur PV utilisable chaque année demandée.")
        print("Une commune absente ne devient pas une commune sans PV. Sens de date_mesure à confirmer.")
    else:
        print("commun : mêmes clés commune/catégorie/grand secteur/NAF, valides chaque année demandée.")
        print("Chaque observation reste une ligne source : aucun total communal ou régional calculé.")
        print("Le changement de détail sectoriel peut réduire fortement l'échantillon commun.")
    print("Codes communs ne garantissent pas des périmètres géographiques stables.")
    print("Les exclusions pour manque, invalidité et répétition peuvent se recouvrir.")
    for category in sorted(frame["category"].unique()):
        print(f"\nCATÉGORIE {category or '(vide)'}")
        subset = stats.loc[stats["categorie"].eq(category)]
        print_table(subset, ["echantillon", "annee", "n_communes_valides", "n_lignes", "n_valides",
                             "n_manquantes", "n_invalides", "n_lignes_repetees", "n_zeros",
                             "mediane", "q25", "q75", "p95", "maximum", "asymetrie"])
        if not args.no_plots:
            groups = [(str(year), frame.loc[frame["year"].eq(year) & frame["category"].eq(category)
                                            & frame["usable"], "value"]) for year in years]
            title = f"{name} — {args.analysis} — {category}"
            plot_histograms(groups, output, f"histogrammes_{slug(category)}", title, unit, args.bins)
            plot_annual_comparison(stats, output, category, title, unit)
    print("\nCSV : quantiles P01/P05/Q25/médiane/Q75/P95/P99, moyenne, écart-type, IQR, asymétrie et effectifs.")
    print("Échantillon commun : sélection plus stricte ; les communes disponibles peuvent être non représentatives.")
    return output


def analyse_production(args, frame, expected):
    monthly = production_statistics(frame, expected, ["mois"])
    hourly = production_statistics(frame, expected, ["heure"])
    month_hour = production_statistics(frame, expected, ["mois", "heure"])
    first, last = expected["mois"].min(), expected["mois"].max()
    output = args.output_dir / f"region_{args.region}" / "production" / f"{first}_{last}"
    output.mkdir(parents=True, exist_ok=True)
    for stem, table in (("statistiques_mensuelles", monthly), ("statistiques_horaires", hourly),
                        ("statistiques_mois_heure", month_hour)):
        table.to_csv(output / f"{stem}.csv", index=False)
    extremes(frame, ["mois"]).to_csv(output / "extremes.csv", index=False)
    print(f"DISTRIBUTIONS PRODUCTION — région {args.region} — {first} à {last}")
    print("Solaire F5 / total des puissances P0. Valeurs converties de Wh en MWh par demi-heure.")
    print("Calendrier Europe/Paris : mois absents et changements d'heure inclus.")
    print("Toutes les occurrences d'un horodatage répété sont exclues des valeurs analysées.")
    print("La couverture porte sur les créneaux, pas sur la quantité d'énergie connue.")
    columns = ["n_attendues", "n_presentes", "n_valides", "n_manquantes", "n_invalides",
               "n_lignes_repetees", "n_zeros", "couverture_pct", "mediane", "p95", "maximum"]
    print("\nPAR MOIS — distributions des demi-heures, pas des totaux mensuels")
    print_table(monthly, ["mois"] + columns + ["complet"])
    print("\nPAR HEURE LOCALE — toutes les dates de la fenêtre")
    print_table(hourly, ["heure"] + columns)
    print(f"\nMois entièrement renseignés : {int(monthly['complet'].sum())}/{len(monthly)}.")
    print("CSV : somme_connue_mwh est partielle ; total_complet_mwh reste vide si la couverture est incomplète.")
    print("Les manques peuvent biaiser les profils observés. Aucune énergie absente remplacée par zéro.")
    if not args.no_plots:
        groups = [(month, frame.loc[frame["mois"].eq(month) & frame["usable"], "value"])
                  for month in monthly["mois"]]
        plot_histograms(groups, output, "histogrammes_demi_heures", f"Production solaire — région {args.region}",
                        "MWh / demi-heure", args.bins)
        plot_production_heatmaps(month_hour, output)
    return output


def region_code(value):
    if not value.isascii() or not value.isdigit() or not 1 <= len(value) <= 2 or int(value) == 0:
        raise argparse.ArgumentTypeError("Code région attendu sur un ou deux chiffres, par exemple 53.")
    return value.zfill(2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", choices=["pv", "consommation", "production"])
    parser.add_argument("--region", type=region_code, default="53")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/rapports/distributions")
    parser.add_argument("--start-year", type=int, help="Année source minimale ; défaut annuel : 2011.")
    parser.add_argument("--end-year", type=int, help="Année source maximale ; défaut annuel : 2025.")
    parser.add_argument("--chunksize", type=int, default=100_000)
    parser.add_argument("--bins", type=int, default=40)
    parser.add_argument("--no-plots", action="store_true", help="Terminal et CSV uniquement.")
    args = parser.parse_args(argv)
    if args.analysis != "production":
        args.start_year = 2011 if args.start_year is None else args.start_year
        args.end_year = 2025 if args.end_year is None else args.end_year
    if any(year is not None and not 1 <= year <= 9998 for year in (args.start_year, args.end_year)):
        parser.error("Années attendues entre 1 et 9998.")
    if args.start_year is not None and args.end_year is not None and args.start_year > args.end_year:
        parser.error("--start-year doit précéder ou égaler --end-year.")
    if args.chunksize <= 0 or args.bins <= 0:
        parser.error("--chunksize et --bins doivent être strictement positifs.")
    try:
        if args.analysis == "production":
            print("Lecture production solaire régionale F5/P0…", file=sys.stderr, flush=True)
            frame, expected, diagnostics = read_production(
                args.data_dir / "production_regionale", args.region, args.start_year, args.end_year, args.chunksize)
            output = analyse_production(args, frame, expected)
        else:
            print("Lecture consommation et rattachement régional…", file=sys.stderr, flush=True)
            frame, departments, name, diagnostics = read_consumption(
                args.data_dir / "consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
                args.region, args.start_year, args.end_year, args.chunksize)
            if args.analysis == "pv":
                print("Lecture parc photovoltaïque communal…", file=sys.stderr, flush=True)
                frame, pv_diagnostics = read_pv(
                    args.data_dir / "puissance_photovoltaique/puissance-solaire-installee-commune.csv",
                    departments, args.start_year, args.end_year, args.chunksize)
                print(f"Rattachement PV par départements : {', '.join(sorted(departments))}.")
                diagnostics.update({f"pv_{key}": count for key, count in pv_diagnostics.items()})
            output = analyse_annual(args, frame, name)
        print("\nLecture : " + " ; ".join(f"{key}={count:,}" for key, count in diagnostics.items()))
        print(f"Sorties : {output}")
        print("Analyses provisoires à rejouer après préparation du module 1. Fichiers source inchangés.")
    except (OSError, ValueError, KeyError, ImportError) as error:
        print(f"Échec de l'analyse : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
