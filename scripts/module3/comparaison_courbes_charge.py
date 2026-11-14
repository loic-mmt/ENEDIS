"""Robustesse du classement des régions selon le fichier de courbes de charge.

Refait le calcul de `classement_regions.py` avec chacun des deux fichiers
(RES2-6-9 et RES2-9-12) et compare les classements obtenus. Si l'ordre des
régions est le même, le résultat ne dépend pas de l'échantillon de clients.
"""

from pathlib import Path
import sys

import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from enedis.scenarios.classement import indicateurs_par_region, regions_absentes
from enedis.scenarios.donnees import (
    ajouter_heure,
    charger_conso_residentielle,
    charger_solaire,
    lire_courbes,
    noms_regions,
    profils_courbes,
)

FICHIERS = ["RES2-6-9", "RES2-9-12"]
ANNEE_CONSO = 2024

conso_res = charger_conso_residentielle(
    ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
    ANNEE_CONSO,
)
solaire = ajouter_heure(charger_solaire(ROOT / "data/raw/production_regionale", [2023, 2024]))
noms = noms_regions(solaire)
for code, nom in regions_absentes(noms, conso_res).items():
    print(f"Région {code} ({nom}) absente de la consommation : ignorée.")

resultats, ids_par_fichier = [], {}
for nom in FICHIERS:
    cc = lire_courbes(ROOT / f"data/raw/courbes_de_charge/{nom}.csv")
    print(f"\n=== {nom} ===")
    print(
        f"Lignes : {len(cc):,} | identifiants : {cc['ID'].nunique()} | "
        f"doublons : {cc.duplicated(['ID', 'horodate']).sum()} | "
        f"valeurs manquantes : {cc['valeur'].isna().sum()}"
    )
    print(cc["valeur"].describe().round(1).to_string())
    print("Période :", cc["horodate"].min(), "->", cc["horodate"].max())
    ids_par_fichier[nom] = set(cc["ID"].unique())
    profils, moyenne = profils_courbes(cc)
    del cc
    res_fichier = indicateurs_par_region(profils, moyenne, conso_res, solaire, noms)
    resultats.append(res_fichier.assign(fichier=nom))
res = pd.concat(resultats, ignore_index=True)

a, b = FICHIERS
commun = len(ids_par_fichier[a] & ids_par_fichier[b])
print(f"\nIdentifiants communs à {a} et {b} : {commun}")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)
for indicateur in ["creux_rel", "rampe_rel"]:
    print(f"\n##### {indicateur} #####")
    for periode in res["periode"].unique():
        t = res[res["periode"] == periode].pivot(
            index="region", columns="fichier", values=indicateur
        )[FICHIERS]
        # Rang 1 = pression la plus forte : creux le plus négatif, rampe la plus grande.
        rangs = t.rank(ascending=(indicateur == "creux_rel"))
        rho = rangs[a].corr(rangs[b])
        print(f"\n{periode} : corrélation des rangs entre les deux fichiers = {rho:.2f}")
        sortie = t.round(2).join(rangs.add_prefix("rang_").astype(int))
        print(sortie.sort_values(f"rang_{a}").to_string())

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
