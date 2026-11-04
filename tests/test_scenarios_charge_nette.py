from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.scenarios.charge_nette import (
    charge_nette,
    consommation_regionale,
    creux_midi,
    indicateurs,
    rampe_soir,
)

HEURES = np.arange(0, 24, 0.5)


def serie(valeurs):
    return pd.Series(valeurs, index=HEURES, dtype=float)


def solaire_en_cloche(pic=60.0):
    s = np.zeros(len(HEURES))
    for i, h in enumerate(HEURES):
        if 8 <= h <= 16:
            s[i] = pic * (1 - ((h - 12) / 4) ** 2)
    return serie(s)


class ConsommationRegionaleTests(unittest.TestCase):
    def test_somme_annuelle_retrouve_la_consommation(self):
        profil = serie(np.linspace(100, 400, len(HEURES)))
        conso = consommation_regionale(profil, profil.mean(), 1_000_000)
        # 365 jours identiques : on doit retrouver la consommation annuelle.
        self.assertAlmostEqual(conso.sum() * 365, 1_000_000, delta=1)

    def test_unite_du_profil_sans_effet(self):
        profil = serie(np.linspace(100, 400, len(HEURES)))
        a = consommation_regionale(profil, profil.mean(), 500_000)
        b = consommation_regionale(profil * 1000, profil.mean() * 1000, 500_000)
        pd.testing.assert_series_equal(a, b)

    def test_entrees_invalides(self):
        profil = serie(np.ones(len(HEURES)))
        with self.assertRaises(ValueError):
            consommation_regionale(profil, 0, 100)
        with self.assertRaises(ValueError):
            consommation_regionale(profil, 1, -5)


class ChargeNetteTests(unittest.TestCase):
    def test_difference_et_non_modification(self):
        conso = serie(np.full(len(HEURES), 100.0))
        sol = solaire_en_cloche()
        conso_avant, sol_avant = conso.copy(), sol.copy()
        net = charge_nette(conso, sol)
        pd.testing.assert_series_equal(net, conso - sol)
        pd.testing.assert_series_equal(conso, conso_avant)
        pd.testing.assert_series_equal(sol, sol_avant)

    def test_heures_differentes_refusees(self):
        conso = serie(np.full(len(HEURES), 100.0))
        sol = solaire_en_cloche().iloc[:-2]
        with self.assertRaises(ValueError):
            charge_nette(conso, sol)


class IndicateursTests(unittest.TestCase):
    def test_creux_au_pic_solaire(self):
        net = charge_nette(serie(np.full(len(HEURES), 40.0)), solaire_en_cloche(60.0))
        valeur, heure = creux_midi(net)
        self.assertAlmostEqual(valeur, -20.0)
        self.assertEqual(heure, 12.0)

    def test_rampe_du_soir(self):
        valeurs = np.full(len(HEURES), 50.0)
        valeurs[HEURES >= 19] = 150.0  # saut de 100 entre 18 h et 19 h, puis plateau
        net = serie(valeurs)
        hausse, heure = rampe_soir(net, debut=16, fin=23, pas_heures=1.0)
        self.assertAlmostEqual(hausse, 100.0)
        self.assertEqual(heure, 18.0)

    def test_rampe_ignore_les_hausses_avant_la_fenetre(self):
        valeurs = np.full(len(HEURES), 50.0)
        valeurs[HEURES >= 7] = 500.0  # grosse hausse le matin, hors fenêtre
        hausse, _ = rampe_soir(serie(valeurs), debut=16, fin=23)
        self.assertAlmostEqual(hausse, 0.0)

    def test_indicateurs_relatifs(self):
        conso = serie(np.full(len(HEURES), 40.0))
        net = charge_nette(conso, solaire_en_cloche(60.0))
        res = indicateurs(net, conso)
        self.assertAlmostEqual(res["creux_rel"], -20.0 / 40.0)
        self.assertEqual(res["heure_creux"], 12.0)

    def test_index_irregulier_refuse(self):
        net = pd.Series([1.0, 2.0, 3.0], index=[0.0, 0.5, 2.0])
        with self.assertRaises(ValueError):
            creux_midi(net)


if __name__ == "__main__":
    unittest.main()