"""Indicateurs de pression (creux de midi, rampe du soir) pour toutes les régions."""

from __future__ import annotations

import pandas as pd

from .charge_nette import charge_nette, consommation_regionale, indicateurs
from .donnees import PERIODES_PAR_DEFAUT, dans_periode


def regions_absentes(noms: pd.Series, conso_res: pd.Series) -> dict:
    """Régions présentes dans la production mais absentes de la consommation."""
    return {code: nom for code, nom in noms.items() if code not in conso_res.index}


def indicateurs_par_region(
    profils: dict,
    moyenne: float,
    conso_res: pd.Series,
    solaire: pd.DataFrame,
    noms: pd.Series,
    periodes: dict | None = None,
) -> pd.DataFrame:
    """Un enregistrement par région et par période, avec les indicateurs de charge nette.

    `solaire` doit contenir code_region, horodate (heure française), heure et mwh.
    Les régions absentes de `conso_res` sont ignorées.
    """
    periodes = periodes or PERIODES_PAR_DEFAUT
    lignes = []
    for code, nom_region in noms.items():
        if code not in conso_res.index:
            continue
        sol_region = solaire[solaire["code_region"] == code]
        for periode, (debut, fin) in periodes.items():
            conso_h = consommation_regionale(profils[periode], moyenne, conso_res[code])
            sol_h = dans_periode(sol_region, debut, fin).groupby("heure")["mwh"].mean()
            net = charge_nette(conso_h, sol_h)
            lignes.append(
                {"region": nom_region, "periode": periode, **indicateurs(net, conso_h)}
            )
    return pd.DataFrame(lignes)
