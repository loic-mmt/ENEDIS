"""Charge nette régionale : consommation estimée moins production solaire.

Toutes les séries sont indexées par l'heure du jour (0, 0.5, ..., 23.5, heure
française) et exprimées en MWh par demi-heure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PAS_HEURES = 0.5
HEURES_PAR_AN = 8760


def _verifier_index_regulier(serie: pd.Series) -> None:
    if len(serie) < 2:
        raise ValueError("La série doit contenir au moins deux points.")
    ecarts = np.diff(serie.index.to_numpy(dtype=float))
    if not np.allclose(ecarts, PAS_HEURES):
        raise ValueError(
            "L'index doit être l'heure du jour, croissant, par pas de 0,5 h."
        )


def consommation_regionale(
    profil: pd.Series, moyenne_annuelle: float, conso_annuelle_mwh: float
) -> pd.Series:
    """Estime la consommation régionale par demi-heure (MWh).

    La région est supposée se comporter comme un client moyen mis à l'échelle :
    on conserve la forme du `profil` et on la cale sur la consommation annuelle.
    L'unité du profil s'annule dans le rapport profil / moyenne_annuelle.
    """
    if moyenne_annuelle <= 0:
        raise ValueError("La moyenne annuelle du profil doit être positive.")
    if conso_annuelle_mwh < 0:
        raise ValueError("La consommation annuelle ne peut pas être négative.")
    return conso_annuelle_mwh * PAS_HEURES * profil / (moyenne_annuelle * HEURES_PAR_AN)


def charge_nette(consommation_mwh: pd.Series, solaire_mwh: pd.Series) -> pd.Series:
    """Consommation moins production solaire, aux mêmes heures du jour."""
    net = consommation_mwh - solaire_mwh
    if net.isna().any() or len(net) != len(consommation_mwh):
        raise ValueError("Les deux séries doivent couvrir les mêmes heures du jour.")
    return net.sort_index()


def creux_midi(net: pd.Series) -> tuple[float, float]:
    """Valeur minimale de la charge nette et heure à laquelle elle est atteinte."""
    _verifier_index_regulier(net)
    return float(net.min()), float(net.idxmin())


def rampe_soir(
    net: pd.Series, debut: float = 16.0, fin: float = 23.0, pas_heures: float = 1.0
) -> tuple[float, float]:
    """Hausse maximale de la charge nette sur `pas_heures`, entre `debut` et `fin`.

    Renvoie (hausse en MWh par demi-heure, heure de début de la hausse).
    """
    _verifier_index_regulier(net)
    n = int(round(pas_heures / PAS_HEURES))
    if n < 1:
        raise ValueError("pas_heures doit valoir au moins 0,5.")
    hausse = net.shift(-n) - net
    fenetre = hausse[(hausse.index >= debut) & (hausse.index <= fin)].dropna()
    if fenetre.empty:
        raise ValueError("Aucune hausse calculable dans la fenêtre demandée.")
    return float(fenetre.max()), float(fenetre.idxmax())


def indicateurs(net: pd.Series, consommation_mwh: pd.Series) -> dict:
    """Creux de midi et rampe du soir, en absolu et relatifs à la consommation moyenne."""
    creux, heure_creux = creux_midi(net)
    rampe, heure_rampe = rampe_soir(net)
    moyenne = float(consommation_mwh.mean())
    if moyenne <= 0:
        raise ValueError("La consommation moyenne doit être positive.")
    return {
        "creux_mwh": creux,
        "heure_creux": heure_creux,
        "rampe_mwh": rampe,
        "heure_rampe": heure_rampe,
        "creux_rel": creux / moyenne,
        "rampe_rel": rampe / moyenne,
    }