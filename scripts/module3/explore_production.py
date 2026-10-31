from pathlib import Path
import pyarrow.dataset as ds

ROOT = Path(__file__).resolve().parents[2]

dataset = ds.dataset(
    ROOT / "data/raw/production_regionale",
    format="parquet",
    partitioning="hive",
    exclude_invalid_files=True,
)

t = dataset.to_table(
    columns=["code_region", "region", "filiere_de_production", "plage_de_puissance_injection"],
    filter=ds.field("year") == 2025,
).to_pandas()

print(t["filiere_de_production"].unique())
print(t["plage_de_puissance_injection"].unique())
print(t[["code_region", "region"]].drop_duplicates())