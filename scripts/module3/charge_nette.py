from pathlib import Path
import pandas as pd
import pyarrow.dataset as ds
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
CODE_REGION = "93"  # PACA : à changer pour tester une autre région
# Hypothèse à confirmer : 'valeur' est une puissance moyenne en W par client.
PERIODES = {
    "Été 2024 (juin-août)": ("2024-06-01", "2024-09-01"),
    "Hiver 2023-24 (déc.-fév.)": ("2023-12-01", "2024-03-01"),
}
paris = lambda s: pd.Timestamp(s, tz="Europe/Paris")

# 1) Profil de consommation d'un client moyen (W), par période et heure du jour.
cc = pd.read_csv(ROOT / "data/raw/courbes_de_charge/RES2-6-9.csv", sep=";", dtype={"ID": str})
cc["horodate"] = pd.to_datetime(cc["horodate"], utc=True).dt.tz_convert("Europe/Paris")
cc["heure"] = cc["horodate"].dt.hour + cc["horodate"].dt.minute / 60
moyenne_annuelle_w = cc["valeur"].mean()
profil_w = {
    nom: cc[(cc["horodate"] >= paris(a)) & (cc["horodate"] < paris(b))]
    .groupby("heure")["valeur"].mean()
    for nom, (a, b) in PERIODES.items()
}
del cc

# 2) Consommation résidentielle annuelle 2024 de la région (MWh).
conso = pd.read_csv(
    ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv",
    usecols=["Année", "Code Région", "CODE CATEGORIE CONSOMMATION", "Conso totale (MWh)"],
    dtype={"Code Région": str},
)
conso = conso[(conso["Année"] == 2024) & (conso["CODE CATEGORIE CONSOMMATION"] == "RES")]
conso_res_mwh = conso.groupby("Code Région")["Conso totale (MWh)"].sum()[CODE_REGION]

# Nombre de "clients moyens équivalents" pour retrouver cette consommation annuelle.
n_equiv = conso_res_mwh * 1e6 / (moyenne_annuelle_w * 8760)
print(f"Région {CODE_REGION} : {conso_res_mwh:,.0f} MWh résidentiels, {n_equiv:,.0f} clients équivalents")

# 3) Production solaire de la région (MWh par demi-heure), mêmes périodes.
prod = ds.dataset(ROOT / "data/raw/production_regionale", format="parquet",
                  partitioning="hive", exclude_invalid_files=True)
sol = prod.to_table(
    columns=["horodate", "total_energie_injectee_wh"],
    filter=(ds.field("year").isin([2023, 2024]) & (ds.field("code_region") == CODE_REGION)
            & (ds.field("filiere_de_production") == "F5 : Solaire")
            & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances")),
).to_pandas()
sol["horodate"] = sol["horodate"].dt.tz_convert("Europe/Paris")
sol["heure"] = sol["horodate"].dt.hour + sol["horodate"].dt.minute / 60
sol["mwh"] = sol["total_energie_injectee_wh"] / 1e6

# 4) Charge nette = consommation - solaire, et graphique.
fig, axes = plt.subplots(1, 2, figsize=(15, 6), sharey=True)
for ax, (nom, (a, b)) in zip(axes, PERIODES.items()):
    conso_mwh = n_equiv * profil_w[nom] * 0.5 / 1e6   # W x 0,5 h = Wh par demi-heure
    solaire = sol[(sol["horodate"] >= paris(a)) & (sol["horodate"] < paris(b))].groupby("heure")["mwh"].mean()
    net = conso_mwh - solaire
    ax.plot(conso_mwh.index, conso_mwh, label="Consommation résidentielle (estimée)")
    ax.plot(solaire.index, solaire, label="Production solaire injectée")
    ax.plot(net.index, net, label="Charge nette", linestyle="--", color="black")
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.set_title(nom)
    ax.set_xlabel("Heure du jour (heure française)")
    ax.grid(alpha=0.3)
axes[0].set_ylabel("MWh par demi-heure")
axes[1].legend(fontsize=8)
fig.suptitle(f"Charge nette moyenne, région {CODE_REGION}")
plt.tight_layout()
plt.show()