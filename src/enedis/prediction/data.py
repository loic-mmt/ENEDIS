from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds


COMMUNE_PATTERN = r"(?:[0-9]{5}|2[AB][0-9]{3})"
DEPARTMENT_PATTERN = r"(?:[0-9]{2}|9[78][0-9]|2[AB])"
CONSUMPTION_CATEGORIES = {
    "CODE CATEGORIE CONSOMMATION": "category",
    "CODE GRAND SECTEUR": "sector",
    "CODE SECTEUR NAF2": "naf",
}


def csv_batches(path, columns=None, chunksize=100_000):
    return pd.read_csv(path, usecols=columns, dtype="string", keep_default_na=False,
                       encoding="utf-8-sig", chunksize=chunksize)


def department_from_code(codes):
    return codes.str[:2].where(~codes.str.startswith(("97", "98")), codes.str[:3])


def valid_measure(values):
    numbers = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    return pd.Series(np.isfinite(numbers) & (numbers >= 0), index=values.index)


def communal_consumption_batches(path, region, start_year, end_year, chunksize, *, categories=False):
    """Yield regional source rows and cumulative metadata; aggregation stays with callers."""
    columns = ["Année", "Code Commune", "Code Département", "Code Région", "Nom Région", "Conso totale (MWh)"]
    extras = CONSUMPTION_CATEGORIES if categories else {}
    departments, names, diagnostics = set(), Counter(), Counter()

    for chunk in csv_batches(path, columns + list(extras), chunksize):
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

        years = pd.to_numeric(selected["Année"].str.strip(), errors="coerce")
        year_valid = years.between(1, 9999) & years.mod(1).eq(0)
        key_valid = codes.str.fullmatch(COMMUNE_PATTERN) & dep_valid & department_from_code(codes).eq(deps)

        diagnostics["invalid_key_rows"] += int((~key_valid | ~year_valid).sum())
        diagnostics["outside_window"] += int((year_valid & ~years.between(start_year, end_year)).sum())
        eligible = key_valid & year_valid & years.between(start_year, end_year)

        frame = pd.DataFrame({
            "commune": codes[eligible], "year": years[eligible].astype(int),
            **{name: selected.loc[eligible, source].str.strip() for source, name in extras.items()},
            "raw_value": selected.loc[eligible, "Conso totale (MWh)"],
        })

        yield frame, departments, names, diagnostics

    if not departments:
        raise ValueError(f"Aucun département trouvé pour la région {region} dans la consommation.")


def communal_pv_batches(path, departments, start_year, end_year, chunksize):
    """Yield published PV rows and cumulative diagnostics, without filling values."""
    columns = ["date_mesure", "geocode_commune", "type_installation", "valeur"]
    diagnostics = Counter()

    for chunk in csv_batches(path, columns, chunksize):
        diagnostics["rows_read"] += len(chunk)
        solar = chunk.loc[chunk["type_installation"].str.strip().eq("Photovoltaïque")]
        codes = solar["geocode_commune"].str.strip()
        code_valid = codes.str.fullmatch(COMMUNE_PATTERN)
        diagnostics["invalid_codes_all_regions"] += int((~code_valid).sum())

        selected = solar.loc[code_valid & department_from_code(codes).isin(departments)]
        diagnostics["region_rows"] += len(selected)

        dates = pd.to_datetime(selected["date_mesure"].str.strip(), errors="coerce", format="mixed")
        years = dates.dt.year
        diagnostics["invalid_dates"] += int(dates.isna().sum())
        diagnostics["outside_window"] += int((dates.notna() & ~years.between(start_year, end_year)).sum())
        eligible = years.between(start_year, end_year)

        yield pd.DataFrame({
            "commune": codes.loc[selected.index][eligible], "year": years[eligible].astype(int),
            "raw_value": selected.loc[eligible, "valeur"],
        }), diagnostics


def solar_batches(source, columns, *, region=None, batch_size=100_000):
    """Scan F5/P0 Parquet batches; ignore sibling metadata files and bound memory."""
    files = sorted(Path(source).rglob("*.parquet")) if isinstance(source, (str, Path)) else list(source)
    if not files:
        raise ValueError(f"Aucun Parquet de production dans {source}.")

    dataset = ds.dataset([str(file) for file in files], format="parquet", partitioning="hive")
    selection = ((ds.field("filiere_de_production") == "F5 : Solaire")
                 & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances"))

    if region is not None:
        selection &= ds.field("code_region") == region

    for batch in dataset.scanner(columns=columns, filter=selection, batch_size=batch_size,
                                 use_threads=False, batch_readahead=1, fragment_readahead=1).to_batches():
        if len(batch):
            yield batch.to_pandas()


def load_all_data(path: Path) -> pd.DataFrame:
    """Load a CSV, a Parquet file, or a partitioned Parquet directory."""
    path = Path(path)

    if path.is_dir():
        if not any(path.rglob("*.parquet")):
            raise ValueError(f"Aucun fichier Parquet dans {path}.")

        return pd.read_parquet(path)

    match path.suffix.lower():
        case ".parquet":
            return pd.read_parquet(path)
        case ".csv":
            return pd.read_csv(path)
        case _:
            raise ValueError(f"Format non pris en charge : {path.suffix}")


def load_filtered_data(path: Path, year: int) -> pd.DataFrame:
    """Load one year from a Parquet dataset exposing a `year` field."""
    production = ds.dataset(Path(path), format="parquet", partitioning="hive")

    if "year" not in production.schema.names:
        raise ValueError(f"Le dataset {path} ne contient pas de champ year.")

    return production.to_table(filter=(ds.field("year") == year)).to_pandas()  # Filtrer avant chargement en pandas.
