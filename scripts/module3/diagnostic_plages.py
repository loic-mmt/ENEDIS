"""Diagnostic : pourquoi les plages P1 à P7 ne somment-elles pas à P0 ?

Pour le solaire, compare le total (P0) à la somme des plages de puissance
P1 à P7 et cherche où se situe l'écart :
- des lignes ou des valeurs absentes dans le détail ;
- ou de l'énergie présente dans le total mais absente du détail,
  même quand les sept plages sont toutes présentes.
"""

from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

ROOT = Path(__file__).resolve().parents[2]
ANNEES = [2023, 2024]
DETAIL = [f"P{i}" for i in range(1, 8)]

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
        "horodate", "region", "code_region", "plage_de_puissance_injection",
        "nb_points_injection", "total_energie_injectee_wh",
    ],
    filter=(
        ds.field("year").isin(ANNEES)
        & (ds.field("filiere_de_production") == "F5 : Solaire")
    ),
).to_pandas()
df["plage"] = df["plage_de_puissance_injection"].str[:2]
df["mwh"] = df["total_energie_injectee_wh"] / 1e6
noms = df.drop_duplicates("code_region").set_index("code_region")["region"]

# A) Contenu de chaque plage : lignes, valeurs absentes, zéros.
print("=== A) Contenu de chaque plage ===")
resume = df.groupby("plage")["mwh"].agg(
    lignes="size",
    nulles=lambda s: int(s.isna().sum()),
    zeros=lambda s: int((s == 0).sum()),
)
resume["part_zeros"] = (resume["zeros"] / resume["lignes"]).round(3)
print(resume.to_string())

# B) Une ligne par (région, horodate), une colonne par plage.
energie = df.set_index(["code_region", "horodate", "plage"])["mwh"].unstack("plage")
points = df.set_index(["code_region", "horodate", "plage"])["nb_points_injection"].unstack("plage")
detail = energie[DETAIL]
t = pd.DataFrame(
    {
        "p0": energie["P0"],
        "somme": detail.sum(axis=1, min_count=1),
        "manquantes": detail.isna().sum(axis=1),
    }
)
t["ecart"] = t["p0"] - t["somme"]


def part(num, den):
    return num.sum() / den.sum() if den.sum() else float("nan")


lignes = []
for code, g in t.groupby(level="code_region"):
    complets = g[g["manquantes"] == 0]
    incomplets = g[g["manquantes"] > 0]
    pts = points.loc[code]
    rapport_points = (pts[DETAIL].sum(axis=1) / pts["P0"]).median()
    lignes.append(
        {
            "region": noms[code],
            "horodates": len(g),
            "part_incomplets": round((g["manquantes"] > 0).mean(), 3),
            "ecart_rel_total": round(part(g["ecart"], g["p0"]), 3),
            "ecart_rel_si_complet": round(part(complets["ecart"], complets["p0"]), 3),
            "ecart_rel_si_incomplet": round(part(incomplets["ecart"], incomplets["p0"]), 3),
            "points_detail/P0": round(float(rapport_points), 3),
        }
    )
bilan = pd.DataFrame(lignes).sort_values("ecart_rel_total", ascending=False)
print("\n=== B) Écart (P0 moins somme P1 à P7) par région ===")
print(bilan.to_string(index=False))

# C) Évolution dans le temps pour les deux régions les plus touchées.
pires = bilan["region"].head(2).tolist()
noms_inverse = {v: k for k, v in noms.items()}
for nom in pires:
    g = t.loc[noms_inverse[nom]].copy()
    g["mois"] = g.index.tz_convert("Europe/Paris").tz_localize(None).to_period("M")
    par_mois = g.groupby("mois").apply(lambda x: part(x["ecart"], x["p0"])).dropna()
    print(f"\n=== C) Écart relatif par mois, {nom} ===")
    print(par_mois.round(3).to_string())

# D) L'écart est-il parfois négatif (détail supérieur au total) ?
negatif = (t["ecart"] < -1e-6).mean()
print(f"\n=== D) Part des horodates où le détail dépasse le total : {negatif:.3f}")

# E) Quand l'énergie d'une plage est vide, y a-t-il des points de raccordement ?
#    points > 0 avec énergie vide : valeur masquée ou non renseignée.
#    points = 0 : aucune installation dans la plage (le vide serait alors un zéro).
vides = df[df["mwh"].isna() & df["plage"].isin(DETAIL)]
print("\n=== E) Énergie vide : nombre de points de raccordement de la plage ===")
if vides.empty:
    print("Aucune valeur vide.")
else:
    e = vides.groupby("plage")["nb_points_injection"].agg(
        lignes="size",
        sans_point=lambda s: int((s == 0).sum()),
        avec_points=lambda s: int((s > 0).sum()),
        points_absents=lambda s: int(s.isna().sum()),
    )
    print(e.to_string())