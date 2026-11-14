"""Robustesse du classement des régions selon la puissance des installations solaires.

Le solaire injecté total (P0) inclut les grandes centrales, alors que la
consommation estimée est résidentielle. On refait le calcul avec le solaire des
petites puissances seulement (plus proches du résidentiel) et on compare les
classements obtenus.

Le profil de consommation est la moyenne des deux fichiers de courbes de charge
(1 000 foyers). Seul le périmètre du solaire change d'une hypothèse à l'autre.

Attention : les valeurs vides des plages P1 à P7 sont comptées comme zéro, ce qui
sous-estime le solaire des petites puissances là où le détail est incomplet
(voir diagnostic_plages.py). Résultat fiable surtout pour Nouvelle-Aquitaine,
Pays de la Loire et Auvergne-Rhône-Alpes.
"""

from pathlib import Path
import sys

import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from enedis.scenarios.classement import indicateurs_par_region, regions_absentes
from enedis.scenarios.donnees import (
    charger_conso_residentielle,
    charger_profils_courbes,
    charger_solaire,
    combiner_profils,
    noms_regions,
    solaire_pour_plages,
)

FICHIERS_COURBES = ["RES2-6-9", "RES2-9-12"]
ANNEE_CONSO = 2024
# Plages : P1 ]0-3] kW, P2 ]3-9] kW, P3 ]9-100] kW, ..., P0 = total.
HYPOTHESES = {
    "Total (P0)": ["P0"],
    "P1 a P3 (100 kW max)": ["P1", "P2", "P3"],
    "P1 a P2 (9 kW max)": ["P1", "P2"],
}
REFERENCE = "Total (P0)"
PERIODES = ["Été 2024", "Hiver 2023-24"]

# Profil de consommation : moyenne des deux fichiers (500 foyers chacun).
profils, moyenne = combiner_profils(
    [charger_profils_courbes(ROOT / f"data/raw/courbes_de_charge/{n}.csv") for n in FICHIERS_COURBES]
)
conso_res = charger_conso_residentielle(
    ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
    ANNEE_CONSO,
)

# Production solaire de toutes les plages de puissance.
sol = charger_solaire(ROOT / "data/raw/production_regionale", [2023, 2024], seulement_total=False)
noms = noms_regions(sol)

# Contrôles : pas de doublon par plage, et P1 à P7 doivent sommer à P0.
doublons = sol.duplicated(["code_region", "horodate", "plage"]).sum()
print("Doublons (région, horodate, plage) :", doublons)
total = sol[sol["plage"] == "P0"].groupby("code_region")["mwh"].sum()
detail = sol[sol["plage"].isin([f"P{i}" for i in range(1, 8)])].groupby("code_region")["mwh"].sum()
rapport = (detail / total).rename(index=noms)
print("Somme des plages P1 à P7 divisée par P0 (attendu : 1) :")
print(rapport.round(3).to_string())

for code, nom in regions_absentes(noms, conso_res).items():
    print(f"Région {code} ({nom}) absente de la consommation : ignorée.")

resultats = []
for nom_hyp, plages in HYPOTHESES.items():
    s = solaire_pour_plages(sol, plages)
    res_hyp = indicateurs_par_region(profils, moyenne, conso_res, s, noms)
    resultats.append(res_hyp.assign(hypothese=nom_hyp))
res = pd.concat(resultats, ignore_index=True)

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", None)
ordre_hyp = list(HYPOTHESES)
for indicateur in ["creux_rel", "rampe_rel"]:
    for periode in PERIODES:
        t = res[res["periode"] == periode].pivot(
            index="region", columns="hypothese", values=indicateur
        )[ordre_hyp]
        # Rang 1 = pression la plus forte : creux le plus négatif, rampe la plus grande.
        rangs = t.rank(ascending=(indicateur == "creux_rel"))
        print(f"\n##### {indicateur} - {periode} #####")
        for nom_hyp in ordre_hyp:
            if nom_hyp != REFERENCE:
                rho = rangs[REFERENCE].corr(rangs[nom_hyp])
                print(f"Corrélation des rangs, {REFERENCE} contre {nom_hyp} : {rho:.2f}")
        if periode == "Été 2024":
            sortie = t.round(2).join(rangs.add_prefix("rang ").astype(int))
            print(sortie.sort_values(f"rang {REFERENCE}").to_string())

ete = res[res["periode"] == "Été 2024"]
ordre = ete[ete["hypothese"] == REFERENCE].sort_values("creux_rel")["region"]
fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
for ax, (colonne, titre) in zip(
    axes,
    [("creux_rel", "Creux de midi relatif, été"), ("rampe_rel", "Rampe du soir relative, été")],
):
    t = ete.pivot(index="region", columns="hypothese", values=colonne)[ordre_hyp].loc[ordre]
    t.plot.barh(ax=ax)
    ax.set_title(titre)
    ax.grid(alpha=0.3)
    ax.axvline(0, color="grey", linewidth=0.8)
axes[0].set_ylabel("")
fig.suptitle("Le classement dépend-il du périmètre du solaire ?")
plt.tight_layout()
plt.show()
