from pathlib import Path
import pandas as pd
import pyarrow.dataset as ds
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
ANNEE = 2025  # une année complète, pour ne pas mélanger saison et croissance du parc

dataset = ds.dataset(
    ROOT / "data/raw/production_regionale",
    format="parquet",
    partitioning="hive",
    exclude_invalid_files=True,
)

df = dataset.to_table(
    columns=["horodate", "region", "code_region", "total_energie_injectee_wh"],
    filter=(
        (ds.field("year") == ANNEE)
        & (ds.field("filiere_de_production") == "F5 : Solaire")
        & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances")
    ),
).to_pandas()

# Contrôle des doublons (doit afficher 0).
doublons = df.duplicated(["code_region", "horodate"]).sum()
print("Lignes :", len(df), "| doublons (région, horodate) :", doublons)

# UTC -> heure française, puis heure du jour, mois et énergie en MWh.
df["horodate"] = df["horodate"].dt.tz_convert("Europe/Paris")
df["heure"] = df["horodate"].dt.hour + df["horodate"].dt.minute / 60
df["mois"] = df["horodate"].dt.month
df["energie_mwh"] = df["total_energie_injectee_wh"] / 1e6

saisons = {"Été (juin-août)": [6, 7, 8], "Hiver (déc.-fév.)": [12, 1, 2]}

fig, axes = plt.subplots(1, 2, figsize=(16, 7), sharey=True)
for ax, (nom, mois) in zip(axes, saisons.items()):
    profils = (
        df[df["mois"].isin(mois)]
        .groupby(["region", "heure"])["energie_mwh"]
        .mean()
        .unstack(0)
    )
    profils.plot(ax=ax, legend=False, colormap="tab20", linewidth=1.8)
    ax.set_title(f"{nom}, {ANNEE}")
    ax.set_xlabel("Heure du jour (heure française)")
    ax.set_xlim(4, 22)  # on zoome sur les heures de jour
    ax.grid(alpha=0.3)

axes[0].set_ylabel("Énergie injectée par demi-heure (MWh, moyenne)")
axes[1].legend(fontsize=8, loc="upper right")
fig.suptitle("Profil journalier solaire par région")
plt.tight_layout()
plt.show()

# Pic moyen d'été par région : pour voir l'ordre des régions.
ete = df[df["mois"].isin([6, 7, 8])]
pics = ete.groupby(["region", "heure"])["energie_mwh"].mean().groupby("region").max()
print(pics.sort_values(ascending=False).round(0))