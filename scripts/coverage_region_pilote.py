#!/usr/bin/env python3
"""Read-only coverage diagnosis for choosing an Enedis pilot region.

Run with the project's Python environment. Output goes to the terminal only.
Missing measurements are counted, never imputed. This is not a data-cleaning
script and does not establish that published sector totals are exhaustive.
"""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyarrow.dataset as ds


ROOT = Path(__file__).resolve().parents[1]
REGIONS = {
    "11": "Île-de-France", "24": "Centre-Val de Loire",
    "27": "Bourgogne-Franche-Comté", "28": "Normandie",
    "32": "Hauts-de-France", "44": "Grand Est", "52": "Pays de la Loire",
    "53": "Bretagne", "75": "Nouvelle-Aquitaine", "76": "Occitanie",
    "84": "Auvergne-Rhône-Alpes", "93": "Provence-Alpes-Côte d'Azur",
}


def valid_measure(values):
    numbers = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    return pd.Series(np.isfinite(numbers) & (numbers >= 0), index=values.index)


def read_consumption(path, start_year, end_year, chunksize):
    columns = ["Année", "Code Commune", "Code Région", "CODE CATEGORIE CONSOMMATION",
               "Conso totale (MWh)"]
    # Bit masks keep only year availability per commune, not millions of source rows.
    communes = defaultdict(lambda: [0, 0, 0, 0])  # present, incomplete, RES present, RES incomplete
    annual = defaultdict(Counter)
    diagnostics = Counter()
    for chunk in pd.read_csv(path, usecols=columns, dtype="string", keep_default_na=False,
                             encoding="utf-8-sig", chunksize=chunksize):
        diagnostics["rows"] += len(chunk)
        years = pd.to_numeric(chunk["Année"].str.strip(), errors="coerce")
        regions = chunk["Code Région"].str.strip()
        codes = chunk["Code Commune"].str.strip()
        valid_year = years.notna() & years.mod(1).eq(0)
        eligible = (valid_year & years.between(start_year, end_year)
                    & regions.isin(REGIONS) & codes.ne(""))
        diagnostics["invalid_key_rows"] += int((~valid_year | regions.eq("") | codes.eq("")).sum())
        diagnostics["outside_window_or_regions"] += int((~eligible & valid_year & regions.ne("") & codes.ne("")).sum())
        frame = pd.DataFrame({
            "region": regions[eligible], "commune": codes[eligible],
            "year": years[eligible].astype(int),
            "known": valid_measure(chunk["Conso totale (MWh)"])[eligible].astype(int),
            "res": chunk.loc[eligible, "CODE CATEGORIE CONSOMMATION"].str.strip().eq("RES").astype(int),
        })
        frame["res_known"] = frame["known"] * frame["res"]
        grouped = frame.groupby(["region", "commune", "year"], sort=False).agg(
            rows=("known", "size"), known=("known", "sum"),
            res=("res", "sum"), res_known=("res_known", "sum"))
        for (region, commune, year), rows, known, res, res_known in (
            (key, *values) for key, values in zip(grouped.index, grouped.itertuples(index=False, name=None))
        ):
            bit = 1 << int(year - start_year)
            state = communes[(region, commune)]
            state[0] |= bit
            if known < rows:
                state[1] |= bit
            if res:
                state[2] |= bit
                if res_known < res:
                    state[3] |= bit
            annual[(region, year)].update(rows=int(rows), known=int(known),
                                           res=int(res), res_known=int(res_known))
    # Complete means all published measurements are usable, not all sectors exist.
    for (region, _), (present, incomplete, res_present, res_incomplete) in communes.items():
        for year in range(start_year, end_year + 1):
            bit = 1 << (year - start_year)
            stats = annual[(region, year)]
            if present & bit:
                stats["communes"] += 1
                stats["all_published_known"] += not bool(incomplete & bit)
            if res_present & bit:
                stats["res_communes"] += 1
                stats["res_all_published_known"] += not bool(res_incomplete & bit)
    return annual, communes, diagnostics


def read_pv(path, start_year, end_year):
    frame = pd.read_csv(path, dtype="string", keep_default_na=False, encoding="utf-8-sig")
    selected = frame.loc[frame["type_installation"].str.strip().eq("Photovoltaïque")].copy()
    dates = pd.to_datetime(selected["date_mesure"], errors="coerce", format="mixed")
    selected["year"] = dates.dt.year
    selected["region"] = selected["geocode_region"].str.strip()
    selected["known"] = valid_measure(selected["valeur"])
    eligible = selected["region"].isin(REGIONS) & selected["year"].between(start_year, end_year)
    annual = {}
    for key, group in selected.loc[eligible].groupby(["region", "year"], sort=False):
        annual[(key[0], int(key[1]))] = {
            "rows": len(group), "known": int(group["known"].sum()),
            "usable": len(group) == 1 and bool(group["known"].iloc[0]),
        }
    diagnostics = {"pv_rows": len(selected), "invalid_dates": int(dates.isna().sum()),
                   "outside_window_or_regions": int((dates.notna() & ~eligible).sum())}
    return annual, diagnostics


def month_bounds(month):
    period = pd.Period(month, freq="M")
    start = period.start_time.tz_localize("Europe/Paris").tz_convert("UTC")
    end = (period + 1).start_time.tz_localize("Europe/Paris").tz_convert("UTC")
    return start, end


def expected_slots(month):
    start, end = month_bounds(month)
    return int((end - start).total_seconds() / 1800)


def read_production(path, batch_size):
    files = sorted(Path(path).rglob("*.parquet"))
    if not files:
        raise ValueError(f"Aucun Parquet de production dans {path}.")
    # metadata.json lives alongside the Parquet files and must not be scanned.
    dataset = ds.dataset([str(file) for file in files], format="parquet", partitioning="hive")
    solar = ((ds.field("filiere_de_production") == "F5 : Solaire")
             & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances"))
    columns = ["code_region", "horodate", "total_energie_injectee_wh"]
    months = defaultdict(lambda: {"rows": 0, "seen": set(), "valid": set(), "duplicates": set()})
    diagnostics = Counter()
    first = last = None
    for batch in dataset.scanner(columns=columns, filter=solar, batch_size=batch_size).to_batches():
        frame = batch.to_pandas()
        diagnostics["rows"] += len(frame)
        regions = frame["code_region"].astype("string").str.strip()
        timestamps = pd.to_datetime(frame["horodate"], utc=True, errors="coerce", format="mixed")
        aligned = (timestamps.notna() & timestamps.dt.minute.mod(30).eq(0)
                   & timestamps.dt.second.eq(0) & timestamps.dt.microsecond.eq(0)
                   & timestamps.dt.nanosecond.eq(0))
        eligible = regions.isin(REGIONS) & aligned
        diagnostics["invalid_time_rows"] += int((~aligned).sum())
        diagnostics["outside_regions"] += int((~regions.isin(REGIONS)).sum())
        if not eligible.any():
            continue
        times = timestamps.loc[eligible]
        minimum, maximum = times.min(), times.max()
        first = min(first, minimum) if first is not None else minimum
        last = max(last, maximum) if last is not None else maximum
        work = pd.DataFrame({
            "region": regions.loc[eligible],
            "month": times.dt.tz_convert("Europe/Paris").dt.strftime("%Y-%m"),
            "slot": times.map(lambda value: int(value.timestamp()) // 1800),
            "known": valid_measure(frame["total_energie_injectee_wh"]).loc[eligible],
        })
        for key, group in work.groupby(["region", "month"], sort=False):
            state = months[key]
            slots = set(group["slot"])
            repeated = set(group.loc[group["slot"].duplicated(keep=False), "slot"])
            state["duplicates"].update(repeated | (state["seen"] & slots))
            state["seen"].update(slots)
            state["valid"].update(group.loc[group["known"], "slot"])
            # An ambiguous duplicate cannot count as a usable measurement.
            state["valid"].difference_update(state["duplicates"])
            state["rows"] += len(group)
    if first is None:
        raise ValueError("Aucune demi-heure solaire F5/P0 exploitable dans les 12 régions.")
    first_month = first.tz_convert("Europe/Paris").strftime("%Y-%m")
    last_month = last.tz_convert("Europe/Paris").strftime("%Y-%m")
    calendar = [str(month) for month in pd.period_range(first_month, last_month, freq="M")]
    # Missing months and regions remain visible in the expected calendar.
    for region in REGIONS:
        for month in calendar:
            state = months[(region, month)]
            state["expected"] = expected_slots(month)
            state["complete"] = len(state["valid"]) == state["expected"]
    return months, calendar, diagnostics


def ratio(known, expected):
    return known / expected if expected else 0.


def rank_regions(consumption, communes, pv, production, calendar, start_year, end_year, min_history):
    expected_years = end_year - start_year + 1
    rows = []
    for region, name in REGIONS.items():
        annual = [consumption.get((region, year), Counter()) for year in range(start_year, end_year + 1)]
        total = sum(item["rows"] for item in annual)
        known = sum(item["known"] for item in annual)
        present_years = sum(item["rows"] > 0 for item in annual)
        # Penalize absent years rather than recommending a one-year series.
        c = ratio(known, total) * present_years / expected_years
        pv_years = sum(pv.get((region, year), {}).get("usable", False)
                       for year in range(start_year, end_year + 1))
        v = pv_years / expected_years
        months = [production[(region, month)] for month in calendar]
        p = ratio(sum(len(item["valid"]) for item in months), sum(item["expected"] for item in months))
        histories = [state for (code, _), state in communes.items() if code == region]
        long_histories = sum((present & ~incomplete).bit_count() >= min_history
                             for present, incomplete, _, _ in histories)
        rows.append({"region": region, "name": name, "consumption": c, "pv": v, "production": p,
                     "years": present_years, "pv_years": pv_years, "communes": len(histories),
                     "long_histories": long_histories, "full_months": sum(item["complete"] for item in months),
                     "score": min(c, v, p), "mean_score": (c + v + p) / 3})
    return sorted(rows, key=lambda row: (-row["score"], -row["mean_score"],
                                          -row["long_histories"], row["region"]))


def print_report(ranking, consumption, pv, production, calendar, diagnostics,
                 start_year, end_year, min_history, details="pilot"):
    print(f"COUVERTURE DES 12 RÉGIONS — fenêtre C/PV : {start_year}–{end_year}")
    print(f"Production : {calendar[0]} à {calendar[-1]} ({len(calendar)} mois calendaires attendus).")
    print("C : mesures utilisables / lignes publiées, pondéré par années présentes.")
    print("PV : années source avec une seule valeur PV utilisable / années demandées.")
    print("P : demi-heures uniques, non ambiguës et renseignées / demi-heures attendues.")
    print("Utilisable = numérique, finie, non négative ; un zéro explicite est conservé.")
    print("Score = minimum de C, PV, P ; départage par leur moyenne, puis historique communal.")
    print()
    header = (f"{'Région':<32} {'C %':>6} {'Ans C':>6} {'PV %':>6} {'P %':>6} "
              f"{'Mois P complets':>16} {'Communes ≥' + str(min_history) + ' ans*':>19} {'Score %':>8}")
    print(header)
    for row in ranking:
        name = f"{row['region']} {row['name']}"
        print(f"{name:<32} {100*row['consumption']:6.1f} {row['years']:6d} {100*row['pv']:6.1f} "
              f"{100*row['production']:6.1f} {str(row['full_months'])+'/'+str(len(calendar)):>16} "
              f"{str(row['long_histories'])+'/'+str(row['communes']):>19} {100*row['score']:8.1f}")
    print("\n* Années où toutes les mesures publiées de la commune sont utilisables.")
    print("Cela ne prouve ni l'exhaustivité sectorielle ni la stabilité des périmètres communaux.")
    best = ranking[0]
    if best["score"] > 0:
        print(f"\nRÉGION PILOTE SUGGÉRÉE (provisoire) : {best['region']} — {best['name']}")
        if best["full_months"] == 0:
            print("ATTENTION : aucun mois de production entièrement renseigné pour cette région.")
            print("Les sommes connues ne sont pas encore des cibles mensuelles complètes ; voir module 1.")
    else:
        print("\nAucune région avec couverture positive des trois sources ; pas de recommandation.")
    print("La sélection compare la disponibilité, pas la quantité d'électricité manquante.")
    print("Les dates PV sont lues sans décalage : leur sens temporel reste à confirmer.")
    print("Le périmètre des gestionnaires du parc PV reste à rapprocher de celui d'Enedis.")
    print("Aucune imputation ni correction. Les cellules absentes et invalides restent indisponibles.")
    c_diag, pv_diag, p_diag = (diagnostics[source] for source in ("C", "PV", "P"))
    print(f"Diagnostic C : {c_diag['rows']:,} lignes lues ; "
          f"{c_diag['invalid_key_rows']:,} clés absentes ou années invalides ; "
          f"{c_diag['outside_window_or_regions']:,} lignes hors fenêtre/régions.")
    print(f"Diagnostic PV : {pv_diag['pv_rows']:,} lignes photovoltaïques ; "
          f"{pv_diag['invalid_dates']:,} dates invalides ; "
          f"{pv_diag['outside_window_or_regions']:,} lignes hors fenêtre/régions.")
    print(f"Diagnostic P : {p_diag['rows']:,} lignes F5/P0 ; "
          f"{p_diag['invalid_time_rows']:,} dates invalides ou hors grille demi-horaire ; "
          f"{p_diag['outside_regions']:,} lignes hors régions.")

    selected = ranking if details == "all" else ranking[:1] if details == "pilot" else []
    for region in selected:
        code = region["region"]
        print(f"\nDÉTAIL — {region['name']} ({code})")
        print(f"{'Année**':<8} {'Lignes C connues':>17} {'Groupes C renseignés*':>23} "
              f"{'Lignes RES connues':>19} {'PV source':>11}")
        for year in range(start_year, end_year + 1):
            c = consumption.get((code, year), Counter())
            v = pv.get((code, year))
            status = "OK" if v and v["usable"] else "ABSENT" if not v else "À VÉRIFIER"
            print(f"{year:<8} {str(c['known'])+'/'+str(c['rows']):>17} "
                  f"{str(c['all_published_known'])+'/'+str(c['communes']):>23} "
                  f"{str(c['res_known'])+'/'+str(c['res']):>19} {status:>11}")
        print("** Année C et année affichée dans la source PV ; équivalence non validée.")
        print(f"\n{'Mois local':<12} {'Créneaux présents':>18} {'Énergies utilisables':>22} {'Répétitions':>13}")
        for month in calendar:
            p = production[(code, month)]
            print(f"{month:<12} {str(len(p['seen']))+'/'+str(p['expected']):>18} "
                  f"{str(len(p['valid']))+'/'+str(p['expected']):>22} {p['rows']-len(p['seen']):>13}")
    print("\nSuite : valider la région et ses périodes avec le module 1 avant les modèles.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--start-year", type=int, default=2011)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--min-history-years", type=int, default=10)
    parser.add_argument("--chunksize", type=int, default=100_000)
    parser.add_argument("--details", choices=["pilot", "all", "none"], default="pilot")
    args = parser.parse_args(argv)
    if not (1 <= args.start_year <= args.end_year <= 9999):
        parser.error("Fenêtre annuelle invalide.")
    if not 1 <= args.min_history_years <= args.end_year - args.start_year + 1:
        parser.error("--min-history-years doit appartenir à la fenêtre annuelle.")
    if args.chunksize <= 0:
        parser.error("--chunksize doit être strictement positif.")
    try:
        raw = args.data_dir
        print("Lecture consommation…", file=sys.stderr, flush=True)
        c, communes, c_diag = read_consumption(
            raw / "consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
            args.start_year, args.end_year, args.chunksize)
        print("Lecture parc photovoltaïque régional…", file=sys.stderr, flush=True)
        pv, pv_diag = read_pv(raw / "puissance_photovoltaique/puissance-solaire-installee-region.csv",
                             args.start_year, args.end_year)
        print("Lecture production solaire régionale F5/P0…", file=sys.stderr, flush=True)
        p, calendar, p_diag = read_production(raw / "production_regionale", args.chunksize)
        ranking = rank_regions(c, communes, pv, p, calendar, args.start_year, args.end_year,
                               args.min_history_years)
        print_report(ranking, c, pv, p, calendar,
                     {"C": c_diag, "PV": pv_diag, "P": p_diag},
                     args.start_year, args.end_year, args.min_history_years, args.details)
    except (OSError, ValueError, KeyError) as error:
        print(f"Échec du diagnostic : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
