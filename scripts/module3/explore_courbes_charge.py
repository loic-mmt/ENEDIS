from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "data/raw/courbes_de_charge/RES2-6-9.csv"

# Seulement 5 lignes : le fichier en fait 8,7 millions.
df = pd.read_csv(path, nrows=5)
print(df.columns.tolist())
print(df.dtypes)
print(df)