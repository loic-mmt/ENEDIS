"""Chargement et préparation des données utilisées par le module 3.

Les séries sont converties en heure française (Europe/Paris), avec une colonne
`heure` (0, 0.5, ..., 23.5) pour construire des profils sur une journée type.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

PERIODES_PAR_DEFAUT = {
    "Été 2024": ("2024-06-01", "2024-09-01"),
    "Hiver 2023-24": ("2023-12-01", "2024-03-01"),
}
FILIERE_SOLAIRE = "F5 : Solaire"
PLAGE_TOTALE = "P0 : Total toutes puissances"
COLONNES_COURBES = {"ID", "horodate", "valeur"}


def paris(texte: str) -> pd.Timestamp:
    """Date (texte) interprétée en heure française."""
    return pd.Timestamp(texte, tz="Europe/Paris")


def ajouter_heure(df: pd.DataFrame) -> pd.DataFrame:
    """Convertit `horodate` en heure française et ajoute la colonne `heure`."""
    df["horodate"] = pd.to_datetime(df["horodate"], utc=True).dt.tz_convert("Europe/Paris")
    df["heure"] = df["horodate"].dt.hour + df["horodate"].dt.minute / 60
    return df


def dans_periode(df: pd.DataFrame, debut: str, fin: str) -> pd.DataFrame:
    """Lignes dont `horodate` est dans [debut, fin[ (dates en heure française)."""
    return df[(df["horodate"] >= paris(debut)) & (df["horodate"] < paris(fin))]


def lire_courbes(chemin) -> pd.DataFrame:
    """Lit un fichier de courbes de charge (séparateur ';') en heure française."""
    cc = pd.read_csv(chemin, sep=";", dtype={"ID": str})
    absentes = COLONNES_COURBES - set(cc.columns)
    if absentes:
        raise ValueError(
            f"{Path(chemin).name} : colonnes absentes {sorted(absentes)} "
            f"(colonnes lues : {list(cc.columns)})"
        )
    return ajouter_heure(cc)


def profils_courbes(cc: pd.DataFrame, periodes: dict | None = None):
    """Profil moyen d'un foyer par période, et moyenne annuelle de `valeur`."""
    periodes = periodes or PERIODES_PAR_DEFAUT
    moyenne = float(cc["valeur"].mean())
    profils = {
        nom: dans_periode(cc, a, b).groupby("heure")["valeur"].mean()
        for nom, (a, b) in periodes.items()
    }
    return profils, moyenne


def charger_profils_courbes(chemin, periodes: dict | None = None):
    """Lit un fichier de courbes de charge et renvoie (profils, moyenne)."""
    return profils_courbes(lire_courbes(chemin), periodes)


def combiner_profils(resultats: list):
    """Moyenne de plusieurs (profils, moyenne), à poids égaux (échantillons de même taille)."""
    if not resultats:
        raise ValueError("Aucun profil à combiner.")
    periodes = resultats[0][0].keys()
    profils = {p: sum(r[0][p] for r in resultats) / len(resultats) for p in periodes}
    moyenne = sum(r[1] for r in resultats) / len(resultats)
    return profils, moyenne


def charger_conso_residentielle(chemin, annee: int) -> pd.Series:
    """Consommation résidentielle annuelle (MWh) par code région."""
    conso = pd.read_csv(
        chemin,
        usecols=["Année", "Code Région", "CODE CATEGORIE CONSOMMATION", "Conso totale (MWh)"],
        dtype={"Code Région": str},
    )
    conso = conso[
        (conso["Année"] == annee) & (conso["CODE CATEGORIE CONSOMMATION"] == "RES")
    ]
    return conso.groupby("Code Région")["Conso totale (MWh)"].sum()


def charger_solaire(dossier, annees, seulement_total: bool = True) -> pd.DataFrame:
    """Production solaire injectée (MWh par demi-heure), toutes régions.

    Colonnes : horodate (UTC), region, code_region, plage (P0 à P7), mwh.
    Avec `seulement_total`, ne garde que le total toutes puissances (P0).
    """
    filtre = ds.field("year").isin(list(annees)) & (
        ds.field("filiere_de_production") == FILIERE_SOLAIRE
    )
    if seulement_total:
        filtre = filtre & (ds.field("plage_de_puissance_injection") == PLAGE_TOTALE)
    dataset = ds.dataset(
        dossier, format="parquet", partitioning="hive", exclude_invalid_files=True
    )
    sol = dataset.to_table(
        columns=[
            "horodate", "region", "code_region",
            "plage_de_puissance_injection", "total_energie_injectee_wh",
        ],
        filter=filtre,
    ).to_pandas()
    sol["plage"] = sol["plage_de_puissance_injection"].str[:2]
    sol["mwh"] = sol["total_energie_injectee_wh"] / 1e6
    return sol[["horodate", "region", "code_region", "plage", "mwh"]]


def noms_regions(solaire: pd.DataFrame) -> pd.Series:
    """Nom de chaque région, indexé par code région."""
    return solaire.drop_duplicates("code_region").set_index("code_region")["region"]


def solaire_pour_plages(solaire: pd.DataFrame, plages: list) -> pd.DataFrame:
    """Solaire de la somme des plages données, par région et demi-heure, en heure française.

    Attention : les valeurs vides d'une plage sont comptées comme zéro dans la somme.
    """
    s = (
        solaire[solaire["plage"].isin(plages)]
        .groupby(["code_region", "horodate"], as_index=False)["mwh"]
        .sum()
    )
    return ajouter_heure(s)
