"""Charge nette et indicateurs de pression pour toutes les régions.

Calcule, pour chaque région et chaque saison type, la charge nette moyenne
(consommation résidentielle estimée moins solaire injecté), puis deux
indicateurs : le creux de midi et la rampe du soir.
Résultat indicatif : consommation résidentielle contre solaire total.
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
    charger_profils_courbes,
    charger_solaire,
    noms_regions,
)

ANNEE_CONSO = 2024

profils, moyenne = charger_profils_courbes(
    ROOT / "data/raw/courbes_de_charge/RES2-6-9.csv"
)
conso_res = charger_conso_residentielle(
    ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
    ANNEE_CONSO,
)
solaire = ajouter_heure(charger_solaire(ROOT / "data/raw/production_regionale", [2023, 2024]))
noms = noms_regions(solaire)

for code, nom in regions_absentes(noms, conso_res).items():
    print(f"Région {code} ({nom}) absente de la consommation : ignorée.")

res = indicateurs_par_region(profils, moyenne, conso_res, solaire, noms)

affichage = res.round(2).sort_values(["periode", "creux_rel"])
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)
print(affichage.to_string(index=False))

# Graphique : indicateurs relatifs, été et hiver côte à côte.
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
