from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.scenarios.classement import indicateurs_par_region, regions_absentes
from enedis.scenarios.donnees import (
    ajouter_heure,
    charger_conso_residentielle,
    charger_profils_courbes,
    charger_solaire,
    combiner_profils,
    dans_periode,
    lire_courbes,
    noms_regions,
    solaire_pour_plages,
)

PERIODES = {"Été": ("2024-06-01", "2024-06-03"), "Hiver": ("2024-01-01", "2024-01-03")}


def ecrire_courbes(chemin, identifiants=("1", "2"), valeur=100.0):
    """Courbes de charge sur janvier et juin 2024, en heure française (décalage +01:00 / +02:00)."""
    lignes = []
    for jour, decalage in [("2024-01-01", "+01:00"), ("2024-01-02", "+01:00"),
                           ("2024-06-01", "+02:00"), ("2024-06-02", "+02:00")]:
        for i in range(48):
            h, m = divmod(i * 30, 60)
            for ident in identifiants:
                lignes.append(f"{ident};{jour} {h:02d}:{m:02d}:00{decalage};{valeur + i}")
    chemin.write_text("ID;horodate;valeur\n" + "\n".join(lignes) + "\n", encoding="utf-8")


def ecrire_solaire(dossier, annee, regions, plages=None):
    """Production solaire d'une année dans un dossier partitionné year=..., avec un metadata.json parasite."""
    plages = plages or ["P0 : Total toutes puissances"]
    horodates = pd.date_range(f"{annee}-01-01", f"{annee}-12-31 23:30", freq="30min", tz="UTC")
    cadres = []
    for code, nom in regions:
        for plage in plages:
            cadres.append(pd.DataFrame({
                "horodate": horodates, "region": nom, "code_region": code,
                "filiere_de_production": "F5 : Solaire",
                "plage_de_puissance_injection": plage,
                "total_energie_injectee_wh": 2e6,
            }))
        cadres.append(pd.DataFrame({  # autre filière : doit être ignorée
            "horodate": horodates, "region": nom, "code_region": code,
            "filiere_de_production": "F4 : Eolien",
            "plage_de_puissance_injection": plages[0],
            "total_energie_injectee_wh": 9e6,
        }))
    partition = dossier / f"year={annee}"
    partition.mkdir(parents=True)
    pq.write_table(pa.Table.from_pandas(pd.concat(cadres)), partition / "part-00001.parquet")
    (dossier / "metadata.json").write_text("{}")


class HeureTests(unittest.TestCase):
    def test_conversion_en_heure_francaise(self):
        df = pd.DataFrame({"horodate": ["2024-01-01T12:00:00Z", "2024-07-01T12:00:00Z"]})
        out = ajouter_heure(df)
        self.assertEqual(list(out["heure"]), [13.0, 14.0])  # UTC+1 en hiver, UTC+2 en été

    def test_dans_periode_demi_ouverte(self):
        df = ajouter_heure(pd.DataFrame({"horodate": [
            "2024-05-31T21:30:00Z",  # 23 h 30 le 31 mai en heure française : avant la période
            "2024-05-31T22:00:00Z",  # 00 h 00 le 1er juin : premier instant inclus
            "2024-06-02T21:30:00Z",  # 23 h 30 le 2 juin : dernier instant inclus
            "2024-06-02T22:00:00Z",  # 00 h 00 le 3 juin : borne de fin exclue
        ]}))
        out = dans_periode(df, "2024-06-01", "2024-06-03")
        self.assertEqual(list(out["heure"]), [0.0, 23.5])


class CourbesTests(unittest.TestCase):
    def test_profils_par_periode(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "RES2.csv"
            ecrire_courbes(chemin)
            profils, moyenne = charger_profils_courbes(chemin, PERIODES)
        self.assertEqual(set(profils), {"Été", "Hiver"})
        self.assertEqual(len(profils["Été"]), 48)
        self.assertEqual(profils["Été"].index[0], 0.0)
        self.assertEqual(profils["Été"].index[-1], 23.5)
        self.assertAlmostEqual(profils["Été"].iloc[0], 100.0)
        self.assertAlmostEqual(profils["Été"].iloc[47], 147.0)
        self.assertAlmostEqual(moyenne, 100.0 + 23.5)

    def test_colonnes_absentes(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "mauvais.csv"
            chemin.write_text("ID;date;val\n1;2024-01-01;3\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                lire_courbes(chemin)
        self.assertIn("horodate", str(ctx.exception))

    def test_combiner_profils(self):
        a = ({"P": pd.Series([2.0, 4.0], index=[0.0, 0.5])}, 10.0)
        b = ({"P": pd.Series([4.0, 8.0], index=[0.0, 0.5])}, 20.0)
        profils, moyenne = combiner_profils([a, b])
        self.assertEqual(list(profils["P"]), [3.0, 6.0])
        self.assertEqual(moyenne, 15.0)
        with self.assertRaises(ValueError):
            combiner_profils([])


class ConsommationTests(unittest.TestCase):
    def test_residentiel_de_l_annee_par_region(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "conso.csv"
            pd.DataFrame({
                "Année": [2024, 2024, 2024, 2023],
                "Code Région": ["93", "93", "93", "93"],
                "CODE CATEGORIE CONSOMMATION": ["RES", "RES", "ENT", "RES"],
                "Conso totale (MWh)": [10.0, 5.0, 100.0, 7.0],
                "autre": [1, 2, 3, 4],
            }).to_csv(chemin, index=False)
            conso = charger_conso_residentielle(chemin, 2024)
        self.assertEqual(conso["93"], 15.0)
        self.assertEqual(list(conso.index), ["93"])


class SolaireTests(unittest.TestCase):
    def test_filtre_filiere_annee_et_plage(self):
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d)
            ecrire_solaire(dossier, 2024, [("93", "PACA"), ("11", "IdF")])
            ecrire_solaire_2023 = dossier / "year=2023"
            ecrire_solaire_2023.mkdir()
            sol = charger_solaire(dossier, [2024])
        self.assertEqual(set(sol["code_region"]), {"93", "11"})
        self.assertEqual(set(sol["plage"]), {"P0"})
        self.assertTrue((sol["mwh"] == 2.0).all())  # 2e6 Wh = 2 MWh, filière éolienne exclue
        self.assertEqual(len(sol), 2 * 365 * 48 + 2 * 48)  # 2024 est bissextile

    def test_noms_et_plages(self):
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d)
            plages = ["P0 : Total toutes puissances", "P1 : ]0 - 3] kW", "P2 : ]3 - 9] kW"]
            ecrire_solaire(dossier, 2024, [("93", "PACA")], plages)
            sol = charger_solaire(dossier, [2024], seulement_total=False)
        self.assertEqual(noms_regions(sol)["93"], "PACA")
        self.assertEqual(set(sol["plage"]), {"P0", "P1", "P2"})
        s = solaire_pour_plages(sol, ["P1", "P2"])
        self.assertTrue((s["mwh"] == 4.0).all())  # P1 + P2 par demi-heure
        self.assertIn("heure", s.columns)


class ClassementTests(unittest.TestCase):
    def test_regions_ignorees_et_colonnes(self):
        heures = np.arange(0, 24, 0.5)
        profils = {"Été": pd.Series(300 + 400 * np.exp(-((heures - 19) / 3) ** 2), index=heures)}
        moyenne = float(profils["Été"].mean())
        conso_res = pd.Series({"93": 1_000_000.0})
        horodates = pd.date_range("2024-06-01", "2024-06-02 23:30", freq="30min", tz="Europe/Paris")
        sol = pd.DataFrame({"horodate": horodates, "code_region": "93", "mwh": 0.0})
        sol["heure"] = sol["horodate"].dt.hour + sol["horodate"].dt.minute / 60
        noms = pd.Series({"93": "PACA", "44": "Grand-Est"})

        self.assertEqual(regions_absentes(noms, conso_res), {"44": "Grand-Est"})
        res = indicateurs_par_region(
            profils, moyenne, conso_res, sol, noms, {"Été": ("2024-06-01", "2024-06-03")}
        )
        self.assertEqual(list(res["region"]), ["PACA"])
        for colonne in ["periode", "creux_mwh", "rampe_mwh", "creux_rel", "rampe_rel"]:
            self.assertIn(colonne, res.columns)
        # Sans solaire, la charge nette est la consommation : le creux est positif.
        self.assertGreater(res.loc[0, "creux_rel"], 0)


if __name__ == "__main__":
    unittest.main()
