"""Charge nette et indicateurs de pression pour toutes les régions.

Calcule, pour chaque région et chaque saison type, la charge nette moyenne
(consommation résidentielle estimée moins solaire injecté), puis deux
indicateurs : le creux de midi et la rampe du soir.
Résultat indicatif : consommation résidentielle contre solaire total.
"""

from pathlib import Path
import sys

import pandas as pd
import pyarrow.dataset as ds
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from enedis.scenarios.charge_nette import (
    charge_nette,
    consommation_regionale,
    indicateurs,
)

ANNEE_CONSO = 2024
PERIODES = {
    "Été 2024": ("2024-06-01", "2024-09-01"),
    "Hiver 2023-24": ("2023-12-01", "2024-03-01"),
}


def paris(texte):
    return pd.Timestamp(texte, tz="Europe/Paris")


def ajouter_heure(df):
    df["horodate"] = pd.to_datetime(df["horodate"], utc=True).dt.tz_convert("Europe/Paris")
    df["heure"] = df["horodate"].dt.hour + df["horodate"].dt.minute / 60
    return df


def dans_periode(df, debut, fin):
    return df[(df["horodate"] >= paris(debut)) & (df["horodate"] < paris(fin))]


# 1) Profil moyen d'un client par période (même unité que 'valeur').
cc = pd.read_csv(
    ROOT / "data/raw/courbes_de_charge/RES2-6-9.csv", sep=";", dtype={"ID": str}
)
cc = ajouter_heure(cc)
moyenne_annuelle = cc["valeur"].mean()
profils_clients = {
    nom: dans_periode(cc, a, b).groupby("heure")["valeur"].mean()
    for nom, (a, b) in PERIODES.items()
}
del cc

# 2) Consommation résidentielle annuelle par région (MWh).
conso = pd.read_csv(
    ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
    usecols=["Année", "Code Région", "CODE CATEGORIE CONSOMMATION", "Conso totale (MWh)"],
    dtype={"Code Région": str},
)
conso = conso[
    (conso["Année"] == ANNEE_CONSO) & (conso["CODE CATEGORIE CONSOMMATION"] == "RES")
]
conso_res = conso.groupby("Code Région")["Conso totale (MWh)"].sum()

# 3) Production solaire de toutes les régions.
prod = ds.dataset(
    ROOT / "data/raw/production_regionale",
    format="parquet",
    partitioning="hive",
    exclude_invalid_files=True,
)
sol = prod.to_table(
    columns=["horodate", "region", "code_region", "total_energie_injectee_wh"],
    filter=(
        ds.field("year").isin([2023, 2024])
        & (ds.field("filiere_de_production") == "F5 : Solaire")
        & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances")
    ),
).to_pandas()
sol = ajouter_heure(sol)
sol["mwh"] = sol["total_energie_injectee_wh"] / 1e6
noms = sol.drop_duplicates("code_region").set_index("code_region")["region"]

# 4) Indicateurs par région et par période.
lignes = []
for code, nom_region in noms.items():
    if code not in conso_res.index:
        print(f"Région {code} ({nom_region}) absente de la consommation : ignorée.")
        continue
    sol_region = sol[sol["code_region"] == code]
    for periode, (a, b) in PERIODES.items():
        conso_h = consommation_regionale(
            profils_clients[periode], moyenne_annuelle, conso_res[code]
        )
        sol_h = dans_periode(sol_region, a, b).groupby("heure")["mwh"].mean()
        net = charge_nette(conso_h, sol_h)
        lignes.append({"region": nom_region, "periode": periode, **indicateurs(net, conso_h)})

res = pd.DataFrame(lignes)
affichage = res.round(2).sort_values(["periode", "creux_rel"])
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)
print(affichage.to_string(index=False))

# 5) Graphique : indicateurs relatifs, été et hiver côte à côte.
ordre = res[res["periode"] == "Été 2024"].sort_values("creux_rel")["region"]
fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
for ax, (colonne, titre) in zip(
    axes,
    [
        ("creux_rel", "Creux de midi (charge nette min. / conso. moyenne)"),
        ("rampe_rel", "Rampe du soir (hausse max. sur 1 h / conso. moyenne)"),
    ],
):
    tableau = res.pivot(index="region", columns="periode", values=colonne).loc[ordre]
    tableau.plot.barh(ax=ax)
    ax.set_title(titre)
    ax.grid(alpha=0.3)
    ax.axvline(0, color="grey", linewidth=0.8)
axes[0].set_ylabel("")
fig.suptitle("Pression potentielle par région (indicatif)")
plt.tight_layout()
plt.show()