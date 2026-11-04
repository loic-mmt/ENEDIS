"""Robustesse du classement des régions selon le fichier de courbes de charge.

Refait le calcul de `classement_regions.py` avec chacun des deux fichiers
(RES2-6-9 et RES2-9-12) et compare les classements obtenus. Si l'ordre des
régions est le même, le résultat ne dépend pas de l'échantillon de clients.
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

FICHIERS = ["RES2-6-9", "RES2-9-12"]
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


def charger_courbes(nom):
    """Lit un fichier de courbes de charge, affiche des contrôles, renvoie les profils."""
    cc = pd.read_csv(
        ROOT / f"data/raw/courbes_de_charge/{nom}.csv", sep=";", dtype={"ID": str}
    )
    attendu = {"ID", "horodate", "valeur"}
    if not attendu <= set(cc.columns):
        raise ValueError(f"{nom} : colonnes inattendues {list(cc.columns)}")
    print(f"\n=== {nom} ===")
    print(
        f"Lignes : {len(cc):,} | identifiants : {cc['ID'].nunique()} | "
        f"doublons : {cc.duplicated(['ID', 'horodate']).sum()} | "
        f"valeurs manquantes : {cc['valeur'].isna().sum()}"
    )
    print(cc["valeur"].describe().round(1).to_string())
    ids = set(cc["ID"].unique())
    cc = ajouter_heure(cc)
    print("Période :", cc["horodate"].min(), "->", cc["horodate"].max())
    moyenne = cc["valeur"].mean()
    profils = {
        periode: dans_periode(cc, a, b).groupby("heure")["valeur"].mean()
        for periode, (a, b) in PERIODES.items()
    }
    del cc
    return profils, moyenne, ids


# Données communes aux deux calculs.
conso = pd.read_csv(
    ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
    usecols=["Année", "Code Région", "CODE CATEGORIE CONSOMMATION", "Conso totale (MWh)"],
    dtype={"Code Région": str},
)
conso = conso[
    (conso["Année"] == ANNEE_CONSO) & (conso["CODE CATEGORIE CONSOMMATION"] == "RES")
]
conso_res = conso.groupby("Code Région")["Conso totale (MWh)"].sum()

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

regions = [(c, n) for c, n in noms.items() if c in conso_res.index]
for c, n in noms.items():
    if c not in conso_res.index:
        print(f"Région {c} ({n}) absente de la consommation : ignorée.")

# Calcul pour chaque fichier.
resultats, ids_par_fichier = [], {}
for nom in FICHIERS:
    profils, moyenne, ids = charger_courbes(nom)
    ids_par_fichier[nom] = ids
    lignes = []
    for code, nom_region in regions:
        sol_region = sol[sol["code_region"] == code]
        for periode, (a, b) in PERIODES.items():
            conso_h = consommation_regionale(profils[periode], moyenne, conso_res[code])
            sol_h = dans_periode(sol_region, a, b).groupby("heure")["mwh"].mean()
            net = charge_nette(conso_h, sol_h)
            lignes.append(
                {"fichier": nom, "region": nom_region, "periode": periode,
                 **indicateurs(net, conso_h)}
            )
    resultats.append(pd.DataFrame(lignes))
res = pd.concat(resultats, ignore_index=True)

# Les deux fichiers contiennent-ils les mêmes clients ?
a, b = FICHIERS
commun = len(ids_par_fichier[a] & ids_par_fichier[b])
print(f"\nIdentifiants communs à {a} et {b} : {commun}")

# Comparaison des classements.
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)
for indicateur in ["creux_rel", "rampe_rel"]:
    print(f"\n##### {indicateur} #####")
    for periode in PERIODES:
        t = res[res["periode"] == periode].pivot(
            index="region", columns="fichier", values=indicateur
        )[FICHIERS]
        # Rang 1 = pression la plus forte : creux le plus négatif, rampe la plus grande.
        rangs = t.rank(ascending=(indicateur == "creux_rel"))
        rho = rangs[a].corr(rangs[b])
        print(f"\n{periode} : corrélation des rangs entre les deux fichiers = {rho:.2f}")
        sortie = t.round(2).join(rangs.add_prefix("rang_").astype(int))
        print(sortie.sort_values(f"rang_{a}").to_string())

# Graphique : indicateurs relatifs d'été pour les deux fichiers.
ordre = (
    res[(res["periode"] == "Été 2024") & (res["fichier"] == a)]
    .sort_values("creux_rel")["region"]
)
fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
for ax, (colonne, titre) in zip(
    axes,
    [("creux_rel", "Creux de midi relatif, été"), ("rampe_rel", "Rampe du soir relative, été")],
):
    t = (
        res[res["periode"] == "Été 2024"]
        .pivot(index="region", columns="fichier", values=colonne)[FICHIERS]
        .loc[ordre]
    )
    t.plot.barh(ax=ax)
    ax.set_title(titre)
    ax.grid(alpha=0.3)
    ax.axvline(0, color="grey", linewidth=0.8)
axes[0].set_ylabel("")
fig.suptitle("Le classement dépend-il du fichier de courbes de charge ?")
plt.tight_layout()
plt.show()