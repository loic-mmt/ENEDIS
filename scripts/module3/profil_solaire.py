from pathlib import Path
import pyarrow.dataset as ds
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
CODE_REGION = "93"  # PACA

dataset = ds.dataset(
    ROOT / "data/raw/production_regionale",
    format="parquet",
    partitioning="hive",
    exclude_invalid_files=True,
)

df = dataset.to_table(
    columns=["horodate", "total_energie_injectee_wh"],
    filter=(
        (ds.field("code_region") == CODE_REGION)
        & (ds.field("filiere_de_production") == "F5 : Solaire")
        & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances")
    ),
).to_pandas()

# Contrôle des doublons : on doit avoir une seule ligne par horodate.
print("Lignes :", len(df), "| horodates uniques :", df["horodate"].nunique())

# UTC -> heure française, puis heure du jour et saison.
df["horodate"] = df["horodate"].dt.tz_convert("Europe/Paris")
df["heure"] = df["horodate"].dt.hour + df["horodate"].dt.minute / 60
df["mois"] = df["horodate"].dt.month
df["energie_mwh"] = df["total_energie_injectee_wh"] / 1e6

saisons = {"Été (juin-août)": [6, 7, 8], "Hiver (déc.-fév.)": [12, 1, 2]}

plt.figure(figsize=(9, 5))
for nom, mois in saisons.items():
    profil = df[df["mois"].isin(mois)].groupby("heure")["energie_mwh"].mean()
    plt.plot(profil.index, profil.values, label=nom)

plt.xlabel("Heure du jour (heure française)")
plt.ylabel("Énergie injectée par demi-heure (MWh, moyenne)")
plt.title("Profil journalier solaire, région 93 (PACA)")
plt.legend()
plt.grid(alpha=0.3)
plt.show()