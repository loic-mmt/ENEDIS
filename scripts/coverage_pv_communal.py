#!/usr/bin/env python3
"""Diagnostiquer la couverture du PV communal et son recoupement avec la consommation.

Lecture seule, sortie terminal. Exemple : --region 53 pour la Bretagne.
Les rapprochements utilisent les codes et années source, sans imputation ni
harmonisation des millésimes géographiques ou des périodes de mesure.
"""

import argparse
from collections import Counter
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
COMMUNE_PATTERN = r"(?:[0-9]{5}|2[AB][0-9]{3})"
DEPARTMENT_PATTERN = r"(?:[0-9]{2}|9[78][0-9]|2[AB])"


def department_from_code(codes):
    """Extraire le département sans convertir les codes communaux en nombres."""
    overseas = codes.str.startswith(("97", "98"))
    return codes.str[:2].where(~overseas, codes.str[:3])


def measure_flags(values):
    numbers = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    valid = np.isfinite(numbers) & (numbers >= 0)
    return pd.Series(valid, index=values.index), pd.Series(valid & (numbers == 0), index=values.index)


def aggregate_parts(parts, columns):
    # Une même clé peut apparaître dans plusieurs lots : agréger après la lecture.
    if parts:
        return pd.concat(parts).groupby(level=["commune", "year"], sort=True).sum()
    index = pd.MultiIndex.from_arrays([[], []], names=["commune", "year"])
    return pd.DataFrame(index=index, columns=columns, dtype="int64")


def read_consumption(path, region, start_year, end_year, chunksize):
    columns = ["Année", "Code Commune", "Code Département", "Code Région",
               "Nom Région", "Conso totale (MWh)"]
    parts, departments, names, diagnostics = [], set(), Counter(), Counter()
    for chunk in pd.read_csv(path, usecols=columns, dtype="string", keep_default_na=False,
                             encoding="utf-8-sig", chunksize=chunksize):
        diagnostics["rows_read"] += len(chunk)
        selected = chunk.loc[chunk["Code Région"].str.strip().str.zfill(2).eq(region)]
        diagnostics["region_rows"] += len(selected)
        if selected.empty:
            continue
        names.update(selected["Nom Région"].str.strip().value_counts().to_dict())
        codes = selected["Code Commune"].str.strip()
        deps = selected["Code Département"].str.strip().str.zfill(2)
        dep_valid = deps.str.fullmatch(DEPARTMENT_PATTERN)
        departments.update(deps[dep_valid])
        code_valid = codes.str.fullmatch(COMMUNE_PATTERN)
        matching_dep = department_from_code(codes).eq(deps)
        key_valid = code_valid & dep_valid & matching_dep
        years = pd.to_numeric(selected["Année"].str.strip(), errors="coerce")
        year_valid = years.between(1, 9999) & years.mod(1).eq(0)
        diagnostics["invalid_key_rows"] += int((~key_valid | ~year_valid).sum())
        diagnostics["outside_window"] += int((year_valid & ~years.between(start_year, end_year)).sum())
        eligible = key_valid & year_valid & years.between(start_year, end_year)
        valid, _ = measure_flags(selected["Conso totale (MWh)"])
        work = pd.DataFrame({"commune": codes[eligible], "year": years[eligible].astype(int),
                             "rows": 1, "known": valid[eligible].astype(int)})
        if not work.empty:
            parts.append(work.groupby(["commune", "year"])[["rows", "known"]].sum())
    if not departments:
        raise ValueError(f"Aucun département trouvé pour la région {region} dans la consommation.")
    name = next((name for name, _ in names.most_common() if name), region)
    return aggregate_parts(parts, ["rows", "known"]), departments, name, diagnostics


def read_pv(path, departments, start_year, end_year, chunksize):
    columns = ["date_mesure", "geocode_commune", "type_installation", "valeur"]
    parts, diagnostics = [], Counter()
    for chunk in pd.read_csv(path, usecols=columns, dtype="string", keep_default_na=False,
                             encoding="utf-8-sig", chunksize=chunksize):
        diagnostics["rows_read"] += len(chunk)
        solar = chunk.loc[chunk["type_installation"].str.strip().eq("Photovoltaïque")]
        codes = solar["geocode_commune"].str.strip()
        code_valid = codes.str.fullmatch(COMMUNE_PATTERN)
        diagnostics["invalid_codes_all_regions"] += int((~code_valid).sum())
        eligible_region = code_valid & department_from_code(codes).isin(departments)
        selected = solar.loc[eligible_region]
        diagnostics["region_rows"] += len(selected)
        if selected.empty:
            continue
        dates = pd.to_datetime(selected["date_mesure"].str.strip(), errors="coerce", format="mixed")
        years = dates.dt.year
        diagnostics["invalid_dates"] += int(dates.isna().sum())
        diagnostics["outside_window"] += int((dates.notna() & ~years.between(start_year, end_year)).sum())
        eligible = years.between(start_year, end_year)
        valid, zeros = measure_flags(selected["valeur"])
        work = pd.DataFrame({"commune": codes.loc[selected.index][eligible],
                             "year": years[eligible].astype(int), "rows": 1,
                             "known": valid[eligible].astype(int), "zeros": zeros[eligible].astype(int)})
        if not work.empty:
            parts.append(work.groupby(["commune", "year"])[["rows", "known", "zeros"]].sum())
    return aggregate_parts(parts, ["rows", "known", "zeros"]), diagnostics


def years_per_commune(frame, mask=None):
    selected = frame if mask is None else frame.loc[mask]
    histories = {}
    for code, year in selected.index:
        histories.setdefault(code, set()).add(int(year))
    return histories


def build_profiles(pv, consumption, start_year, end_year):
    sources = {
        "pv_present": years_per_commune(pv),
        # Toute répétition rend la commune/année ambiguë, même à valeur identique.
        "pv_usable": years_per_commune(pv, pv["rows"].eq(1) & pv["known"].eq(1)),
        "pv_duplicates": years_per_commune(pv, pv["rows"].gt(1)),
        "pv_invalid": years_per_commune(pv, pv["known"].lt(pv["rows"])),
        "c_present": years_per_commune(consumption),
        "c_known": years_per_commune(consumption, consumption["rows"].eq(consumption["known"])),
    }
    codes = sorted(set(sources["pv_present"]) | set(sources["c_present"]))
    window = set(range(start_year, end_year + 1))
    profiles = {}
    for code in codes:
        profile = {key: source.get(code, set()) for key, source in sources.items()}
        present = profile["pv_present"]
        between = set(range(min(present), max(present) + 1)) if present else set()
        profile["internal_missing"] = between - present
        profile["window_absent"] = window - present
        profile["common_present"] = present & profile["c_present"]
        profile["common_known"] = profile["pv_usable"] & profile["c_known"]
        profiles[code] = profile
    return profiles


def longest_run(years):
    longest = current = 0
    previous = None
    for year in sorted(years):
        current = current + 1 if previous is not None and year == previous + 1 else 1
        longest = max(longest, current)
        previous = year
    return longest


def format_years(years):
    ordered = sorted(years)
    ranges = []
    for year in ordered:
        if ranges and year == ranges[-1][1] + 1:
            ranges[-1][1] = year
        else:
            ranges.append([year, year])
    return ", ".join(str(first) if first == last else f"{first}–{last}" for first, last in ranges) or "—"


def print_examples(label, examples, limit):
    examples = list(examples)
    print(f"{label} : {len(examples)}")
    if examples:
        print("  " + " ; ".join(examples[:limit]))
        if len(examples) > limit:
            print(f"  … {len(examples) - limit} autres ; --details all pour le détail par commune.")


def print_report(pv, consumption, profiles, departments, name, region, diagnostics,
                 start_year, end_year, min_history, details="summary", max_examples=10):
    count_years = end_year - start_year + 1
    pv_codes = {code for code, p in profiles.items() if p["pv_present"]}
    c_codes = {code for code, p in profiles.items() if p["c_present"]}
    print(f"COUVERTURE PV COMMUNAL — {name} ({region}) — {start_year}–{end_year}")
    print(f"Départements issus de la consommation : {', '.join(sorted(departments))}.")
    print("PV rattaché par préfixe du code commune ; communes absentes de la consommation incluses.")
    print("PV utilisable = une seule ligne commune/année, valeur numérique, finie et non négative.")
    print("C renseignée* = toutes les mesures publiées de la commune/année sont renseignées et valides.")
    print("Un zéro explicite reste valide ; aucun manque remplacé, aucun doublon supprimé.")
    print(f"\nCodes communaux observés dans la fenêtre : PV {len(pv_codes)}, consommation {len(c_codes)}, "
          f"dans les deux (au moins une année chacun) {len(pv_codes & c_codes)}.")
    print("Ces effectifs ne constituent pas un référentiel exhaustif des communes de la région.")
    print(f"\n{'Année':<6} {'PV prés.':>9} {'PV utilis.':>11} {'Doubl. PV':>10} {'C prés.':>9} "
          f"{'C renseig.*':>12} {'C/PV prés.':>11} {'C/PV renseig.*':>15}")
    for year in range(start_year, end_year + 1):
        counts = {key: sum(year in p[key] for p in profiles.values()) for key in
                  ("pv_present", "pv_usable", "pv_duplicates", "c_present", "c_known",
                   "common_present", "common_known")}
        print(f"{year:<6} {counts['pv_present']:9d} {counts['pv_usable']:11d} {counts['pv_duplicates']:10d} "
              f"{counts['c_present']:9d} {counts['c_known']:12d} {counts['common_present']:11d} "
              f"{counts['common_known']:15d}")
    print("C/PV : même code ET même année affichée dans les deux sources.")
    print("Doubl. PV : nombre de clés commune/année répétées, pas nombre de lignes supplémentaires.")

    print("\nHISTORIQUES — nombre de communes par nombre d'années dans la fenêtre")
    print(f"{'Nb années':<10} {'PV présentes':>14} {'PV utilisables':>16} {'C/PV renseignées*':>19}")
    lengths = {key: Counter(len(p[key]) for p in profiles.values())
               for key in ("pv_present", "pv_usable", "common_known")}
    for length in range(count_years + 1):
        if any(counts[length] for counts in lengths.values()):
            print(f"{length:<10} {lengths['pv_present'][length]:14d} {lengths['pv_usable'][length]:16d} "
                  f"{lengths['common_known'][length]:19d}")
    for key, label in (("pv_usable", "PV utilisable"), ("common_known", "C/PV renseignées*")):
        long = sum(len(p[key]) >= min_history for p in profiles.values())
        consecutive = sum(longest_run(p[key]) >= min_history for p in profiles.values())
        full = sum(len(p[key]) == count_years for p in profiles.values())
        print(f"{label} : ≥ {min_history} ans {long} communes ; ≥ {min_history} ans consécutifs "
              f"{consecutive} ; fenêtre entière {full}.")

    print("\nABSENCES ET RÉPÉTITIONS — exemples limités")
    print("Trou interne = année sans ligne PV entre première et dernière années PV présentes.")
    print("Les absences aux extrémités restent distinctes ; aucune absence ne prouve un parc nul.")
    print_examples("Codes uniquement dans la consommation", sorted(c_codes - pv_codes), max_examples)
    print_examples("Codes uniquement dans le PV", sorted(pv_codes - c_codes), max_examples)
    print_examples("Communes avec trous PV internes",
                   (f"{code} : {format_years(p['internal_missing'])}" for code, p in profiles.items()
                    if p["internal_missing"]), max_examples)
    print_examples("Communes avec valeurs PV absentes ou invalides",
                   (f"{code} : {format_years(p['pv_invalid'])}" for code, p in profiles.items()
                    if p["pv_invalid"]), max_examples)
    repeated = pv.loc[pv["rows"].gt(1)]
    extra = int((repeated["rows"] - 1).sum())
    print_examples(f"Clés PV répétées ({extra} lignes supplémentaires)",
                   (f"{code}/{year} : {int(row.rows)} lignes" for (code, year), row in repeated.iterrows()),
                   max_examples)

    c_diag, pv_diag = diagnostics
    print(f"\nLECTURE C : {c_diag['rows_read']:,} lignes parcourues ; {c_diag['region_rows']:,} "
          f"dans la région ; {c_diag['invalid_key_rows']:,} clés invalides/incohérentes ; "
          f"{c_diag['outside_window']:,} lignes hors fenêtre.")
    print(f"LECTURE PV : {pv_diag['rows_read']:,} lignes parcourues ; {pv_diag['region_rows']:,} "
          f"lignes photovoltaïques de la région ; {pv_diag['invalid_dates']:,} dates invalides ; "
          f"{pv_diag['outside_window']:,} lignes hors fenêtre.")
    print(f"PV dans la fenêtre : {int(pv['rows'].sum()):,} lignes ; "
          f"{int((pv['rows'] - pv['known']).sum()):,} valeurs absentes/invalides ; "
          f"{int(pv['zeros'].sum()):,} zéros explicites.")
    print(f"Codes PV invalides, toutes régions (non attribuables) : "
          f"{pv_diag['invalid_codes_all_regions']:,} lignes photovoltaïques.")
    if not pv_codes or not c_codes:
        print("ATTENTION : une source est absente de la fenêtre régionale ; recoupement indisponible.")
    print("\n* Toutes les valeurs publiées connues ne prouvent pas un total sectoriel exhaustif.")
    print("Dates PV conservées sans décalage ; équivalence avec l'année de consommation à confirmer.")
    print("Codes comparés tels que publiés : fusions, changements de code et millésimes non harmonisés.")
    print("Rattachement département/région issu du fichier C ; existence officielle des codes non validée.")
    print("Diagnostic de disponibilité uniquement ; corrections et complétions relèvent du module 1.")

    if details != "summary":
        print("\nDÉTAIL PAR COMMUNE — années dans la fenêtre demandée")
        for code, p in profiles.items():
            if details == "gaps" and not (p["internal_missing"] or p["pv_duplicates"] or p["pv_invalid"]):
                continue
            print(f"{code} : PV {len(p['pv_present'])}/{count_years} présentes, "
                  f"{len(p['pv_usable'])} utilisables ; C/PV renseignées* {len(p['common_known'])} ; "
                  f"absentes {format_years(p['window_absent'])} ; "
                  f"trous internes {format_years(p['internal_missing'])} ; "
                  f"invalides {format_years(p['pv_invalid'])} ; "
                  f"répétées {format_years(p['pv_duplicates'])}.")


def region_code(value):
    if not value.isascii() or not value.isdigit() or not 1 <= len(value) <= 2 or int(value) == 0:
        raise argparse.ArgumentTypeError("Code région attendu sur un ou deux chiffres, par exemple 53.")
    return value.zfill(2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", type=region_code, default="53", help="Code région INSEE (défaut : 53).")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--start-year", type=int, default=2011)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--min-history-years", type=int, default=None,
                        help="Seuil d'historique (défaut : 10, limité à la fenêtre demandée).")
    parser.add_argument("--chunksize", type=int, default=100_000)
    parser.add_argument("--details", choices=["summary", "gaps", "all"], default="summary",
                        help="Résumé, communes avec trous/doublons/invalides, ou toutes les communes.")
    parser.add_argument("--max-examples", type=int, default=10)
    args = parser.parse_args(argv)
    if not 1 <= args.start_year <= args.end_year <= 9999:
        parser.error("Fenêtre annuelle invalide.")
    min_history = (args.min_history_years if args.min_history_years is not None
                   else min(10, args.end_year - args.start_year + 1))
    if not 1 <= min_history <= args.end_year - args.start_year + 1:
        parser.error("--min-history-years doit appartenir à la fenêtre annuelle.")
    if args.chunksize <= 0 or args.max_examples <= 0:
        parser.error("--chunksize et --max-examples doivent être strictement positifs.")
    try:
        print(f"Lecture consommation — région {args.region}…", file=sys.stderr, flush=True)
        c, departments, name, c_diag = read_consumption(
            args.data_dir / "consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
            args.region, args.start_year, args.end_year, args.chunksize)
        print("Lecture parc photovoltaïque communal…", file=sys.stderr, flush=True)
        pv, pv_diag = read_pv(args.data_dir / "puissance_photovoltaique/puissance-solaire-installee-commune.csv",
                             departments, args.start_year, args.end_year, args.chunksize)
        profiles = build_profiles(pv, c, args.start_year, args.end_year)
        print_report(pv, c, profiles, departments, name, args.region, (c_diag, pv_diag),
                     args.start_year, args.end_year, min_history, args.details, args.max_examples)
    except (OSError, ValueError, KeyError) as error:
        print(f"Échec du diagnostic : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
