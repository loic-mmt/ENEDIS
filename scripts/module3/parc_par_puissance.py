"""Parc d'installations solaires par classe de puissance et son évolution.

Utilise `nb_points_injection` (nombre de points de raccordement), qui est
renseigné pour toutes les plages P1 à P7, contrairement à l'énergie. Donne,
pour chaque région, le nombre de points par plage et sa croissance, qui peut
servir à construire les scénarios solaire.

Petites puissances : P1 à P3 (jusqu'à 100 kW). Grandes : P4 à P7.
"""

from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
DETAIL = [f"P{i}" for i in range(1, 8)]
PETITES = ["P1", "P2", "P3"]
GRANDES = ["P4", "P5", "P6", "P7"]

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", None)

dataset = ds.dataset(
    ROOT / "data/raw/production_regionale",
    format="parquet",
    partitioning="hive",
    exclude_invalid_files=True,
)
df = dataset.to_table(
    columns=[
        "horodate", "region", "code_region",
        "plage_de_puissance_injection", "nb_points_injection",
    ],
    filter=ds.field("filiere_de_production") == "F5 : Solaire",
).to_pandas()
df["plage"] = df["plage_de_puissance_injection"].str[:2]
df["horodate"] = df["horodate"].dt.tz_convert("Europe/Paris")
noms = df.drop_duplicates("code_region").set_index("code_region")["region"]
print("Période :", df["horodate"].min(), "->", df["horodate"].max())
print("Valeurs absentes de nb_points_injection :", int(df["nb_points_injection"].isna().sum()))

# Contrôle : le nombre de points varie-t-il au cours de la journée ?
premiere = df["code_region"].iloc[0]
test = df[(df["code_region"] == premiere) & (df["plage"] == "P0")]
par_heure = test.groupby(test["horodate"].dt.hour)["nb_points_injection"].median()
print(
    f"\nNombre de points (P0, {noms[premiere]}) par heure du jour : "
    f"min {par_heure.min():.0f}, max {par_heure.max():.0f}"
)

# Nombre de points par jour = maximum de la journée (robuste à une variation horaire),
# puis médiane par mois.
df["jour"] = df["horodate"].dt.date
quotidien = (
    df.groupby(["code_region", "plage", "jour"])["nb_points_injection"].max().reset_index()
)
quotidien["mois"] = pd.to_datetime(quotidien["jour"]).dt.to_period("M")
mensuel = (
    quotidien.groupby(["code_region", "plage", "mois"])["nb_points_injection"]
    .median()
    .reset_index()
)

premier_mois, dernier_mois = mensuel["mois"].min(), mensuel["mois"].max()
print(f"\nPremier mois : {premier_mois} | dernier mois : {dernier_mois}")


def points(mois, plages):
    m = mensuel[(mensuel["mois"] == mois) & (mensuel["plage"].isin(plages))]
    return m.groupby("code_region")["nb_points_injection"].sum()


tableau = pd.DataFrame(
    {
        "total_debut": points(premier_mois, ["P0"]),
        "total_fin": points(dernier_mois, ["P0"]),
        "petites_debut": points(premier_mois, PETITES),
        "petites_fin": points(dernier_mois, PETITES),
        "grandes_debut": points(premier_mois, GRANDES),
        "grandes_fin": points(dernier_mois, GRANDES),
    }
)
tableau["croiss_total_%"] = (tableau["total_fin"] / tableau["total_debut"] - 1) * 100
tableau["croiss_petites_%"] = (tableau["petites_fin"] / tableau["petites_debut"] - 1) * 100
tableau["croiss_grandes_%"] = (tableau["grandes_fin"] / tableau["grandes_debut"] - 1) * 100
tableau["part_petites_fin_%"] = tableau["petites_fin"] / tableau["total_fin"] * 100
tableau.index = tableau.index.map(noms)
print("\n=== Points de raccordement par région (début et fin de période) ===")
print(tableau.round(1).sort_values("total_fin", ascending=False).to_string())

# Contrôle de cohérence : P1 à P7 doivent sommer à P0.
somme_fin = points(dernier_mois, DETAIL)
rapport = (somme_fin / points(dernier_mois, ["P0"])).rename(index=noms)
print("\nSomme P1 à P7 divisée par P0 en fin de période (attendu : 1) :")
print(rapport.round(3).to_string())

# Graphique : évolution mensuelle du nombre de points, petites puis grandes puissances.
fig, axes = plt.subplots(1, 2, figsize=(15, 6))
for ax, (plages, titre) in zip(
    axes, [(PETITES, "Petites puissances (P1 à P3, jusqu'à 100 kW)"), (GRANDES, "Grandes puissances (P4 à P7)")]
):
    m = mensuel[mensuel["plage"].isin(plages)]
    serie = m.groupby(["mois", "code_region"])["nb_points_injection"].sum().unstack("code_region")
    serie.index = serie.index.to_timestamp()
    serie.columns = [noms[c] for c in serie.columns]
    serie.plot(ax=ax, legend=False)
    ax.set_title(titre)
    ax.set_xlabel("")
    ax.grid(alpha=0.3)
axes[0].set_ylabel("Nombre de points de raccordement")
axes[1].legend(fontsize=8, loc="upper left")
fig.suptitle("Parc solaire par classe de puissance")
plt.tight_layout()
plt.show()