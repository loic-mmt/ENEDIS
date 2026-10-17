from pathlib import Path
import pandas as pd
import pyarrow.dataset as ds


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
    production = ds.dataset(
        Path(path),
        format="parquet",
        partitioning="hive",
    )

    if "year" not in production.schema.names:
        raise ValueError(f"Le dataset {path} ne contient pas de champ year.")
    return production.to_table(filter=(ds.field("year") == year)).to_pandas()
