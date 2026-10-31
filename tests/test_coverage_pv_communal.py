import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/coverage_pv_communal.py"
spec = importlib.util.spec_from_file_location("coverage_pv_communal", SCRIPT)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


class CommunalCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c_path = self.root / "consommation/consommation-electrique-par-secteur-dactivite-commune.csv"
        self.pv_path = self.root / "puissance_photovoltaique/puissance-solaire-installee-commune.csv"
        self.c_path.parent.mkdir()
        self.pv_path.parent.mkdir()
        pd.DataFrame([
            [2020, "22001", "22", "53", "Bretagne", 0],
            [2021, "22001", "22", "53", "Bretagne", 10],
            [2022, "22001", "22", "53", "Bretagne", 12],
            [2023, "22001", "22", "53", "Bretagne", 13],
            [2020, "22002", "22", "53", "Bretagne", 0],
            [2023, "22002", "22", "53", "Bretagne", 3],
            [2021, "22003", "22", "53", "Bretagne", 4],
            [2020, "37001", "37", "24", "Centre-Val de Loire", 1],
            [2020, "2A001", "2A", "94", "Corse", 2],
            [2020, "97101", "971", "01", "Guadeloupe", 2],
            [2010, "29001", "29", "53", "Bretagne", 1],
            # La seconde ligne publiée est dans un autre lot et reste manquante.
            [2020, "22001", "22", "53", "Bretagne", ""],
        ], columns=["Année", "Code Commune", "Code Département", "Code Région",
                    "Nom Région", "Conso totale (MWh)"]).to_csv(self.c_path, index=False)
        pd.DataFrame([
            ["2020-01-01", "22001", "Photovoltaïque", 0],
            ["2022-01-01", "22001", "Photovoltaïque", 12],
            ["2023-01-01", "22001", "Photovoltaïque", 13],
            ["2020-01-01", "22002", "Photovoltaïque", ""],
            ["2021-01-01", "22002", "Photovoltaïque", 2],
            ["2023-01-01", "22002", "Photovoltaïque", -1],
            ["2022-01-01", "22004", "Photovoltaïque", 4],
            ["2023-01-01", "29002", "Photovoltaïque", 5],
            ["2019-01-01", "22001", "Photovoltaïque", 5],
            ["inconnue", "22001", "Photovoltaïque", 5],
            ["2022-01-01", "22001", "Solaire thermique", 5],
            ["2020-01-01", "37001", "Photovoltaïque", 1],
            ["2020-01-01", "2A001", "Photovoltaïque", 1],
            ["2020-01-01", "97101", "Photovoltaïque", 1],
            ["2020-01-01", "invalide", "Photovoltaïque", 1],
            # Deux dates distinctes dans une même année restent ambiguës pour la cible annuelle.
            ["2021-06-01", "22002", "Photovoltaïque", 3],
        ], columns=["date_mesure", "geocode_commune", "type_installation", "valeur"]).to_csv(
            self.pv_path, index=False)

    def read_region(self, region="53", chunksize=1):
        c, departments, name, c_diag = coverage.read_consumption(
            self.c_path, region, 2020, 2023, chunksize)
        pv, pv_diag = coverage.read_pv(self.pv_path, departments, 2020, 2023, chunksize)
        return c, pv, departments, name, c_diag, pv_diag

    def test_region_mapping_includes_pv_only_communes(self):
        c, pv, departments, name, c_diag, pv_diag = self.read_region()
        self.assertEqual(departments, {"22", "29"})
        self.assertEqual(name, "Bretagne")
        self.assertEqual(set(c.index.get_level_values("commune")), {"22001", "22002", "22003"})
        self.assertEqual(set(pv.index.get_level_values("commune")), {"22001", "22002", "22004", "29002"})
        self.assertEqual(c_diag["outside_window"], 1)
        self.assertEqual(pv_diag["outside_window"], 1)
        self.assertEqual(pv_diag["invalid_dates"], 1)
        self.assertEqual(pv_diag["invalid_codes_all_regions"], 1)

    def test_gaps_distinguish_internal_absence_invalid_value_and_edges(self):
        c, pv, *_ = self.read_region()
        profiles = coverage.build_profiles(pv, c, 2020, 2023)
        a, b, only = profiles["22001"], profiles["22002"], profiles["22004"]
        self.assertEqual(a["internal_missing"], {2021})
        self.assertEqual(a["pv_usable"], {2020, 2022, 2023})
        self.assertEqual(a["common_present"], {2020, 2022, 2023})
        self.assertEqual(a["common_known"], {2022, 2023})
        self.assertEqual(b["internal_missing"], {2022})
        self.assertEqual(b["pv_invalid"], {2020, 2023})
        self.assertEqual(b["pv_usable"], set())
        self.assertEqual(only["internal_missing"], set())
        self.assertEqual(only["window_absent"], {2020, 2021, 2023})
        self.assertEqual(coverage.longest_run(a["pv_usable"]), 2)

    def test_duplicates_across_chunks_and_explicit_zeros(self):
        c, pv, *_ = self.read_region(chunksize=1)
        self.assertEqual(pv.loc[("22002", 2021), "rows"], 2)
        self.assertEqual(pv.loc[("22002", 2021), "known"], 2)
        self.assertEqual(pv.loc[("22001", 2020), "known"], 1)
        self.assertEqual(pv.loc[("22001", 2020), "zeros"], 1)
        self.assertEqual(c.loc[("22001", 2020), "rows"], 2)
        self.assertEqual(c.loc[("22001", 2020), "known"], 1)
        whole = self.read_region(chunksize=100)
        pd.testing.assert_frame_equal(c, whole[0])
        pd.testing.assert_frame_equal(pv, whole[1])

    def test_other_regions_corsica_and_overseas_need_no_code_change(self):
        for region, code, department in [("24", "37001", "37"), ("94", "2A001", "2A"),
                                         ("01", "97101", "971")]:
            with self.subTest(region=region):
                c, pv, departments, *_ = self.read_region(region)
                self.assertEqual(departments, {department})
                self.assertEqual(list(c.index), [(code, 2020)])
                self.assertEqual(list(pv.index), [(code, 2020)])
        self.assertEqual(coverage.region_code("1"), "01")

    def test_invalid_consumption_keys_and_nonfinite_pv_values_not_usable(self):
        c = pd.read_csv(self.c_path, dtype=str, keep_default_na=False)
        c.loc[0, "Code Commune"] = "37009"  # Département incompatible avec 22.
        c.to_csv(self.c_path, index=False)
        pv = pd.read_csv(self.pv_path, dtype=str, keep_default_na=False)
        pv.loc[1, "valeur"] = "inf"
        pv.loc[2, "valeur"] = "texte"
        pv.to_csv(self.pv_path, index=False)
        c, pv, _, _, c_diag, _ = self.read_region()
        self.assertNotIn(("37009", 2020), c.index)
        self.assertEqual(c_diag["invalid_key_rows"], 1)
        profiles = coverage.build_profiles(pv, c, 2020, 2023)
        self.assertEqual(profiles["22001"]["pv_usable"], {2020})
        self.assertEqual(profiles["22001"]["pv_invalid"], {2022, 2023})

    def test_unknown_region_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Aucun département trouvé pour la région 99"):
            coverage.read_consumption(self.c_path, "99", 2020, 2023, 2)

    def test_empty_pv_window_reports_absence_instead_of_zero_capacity(self):
        c, departments, name, c_diag = coverage.read_consumption(self.c_path, "53", 2020, 2023, 2)
        pv, pv_diag = coverage.read_pv(self.pv_path, departments, 2026, 2027, 2)
        profiles = coverage.build_profiles(pv, c, 2020, 2023)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            coverage.print_report(pv, c, profiles, departments, name, "53", (c_diag, pv_diag),
                                  2020, 2023, 2)
        self.assertEqual(len(profiles), 3)
        self.assertIn("une source est absente", output.getvalue())
        self.assertIn("aucune absence ne prouve un parc nul", output.getvalue())

    def test_cli_report_is_terminal_only_and_preserves_inputs(self):
        before = {str(p.relative_to(self.root)): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = coverage.main(["--data-dir", str(self.root), "--region", "53",
                                    "--start-year", "2020", "--end-year", "2023",
                                    "--chunksize", "2", "--details", "all", "--max-examples", "1"])
        self.assertEqual(status, 0, errors.getvalue())
        text = output.getvalue()
        self.assertIn("Bretagne (53)", text)
        self.assertIn("22002/2021 : 2 lignes", text)
        self.assertIn("trous internes 2021", text)
        self.assertIn("équivalence avec l'année de consommation à confirmer", text)
        self.assertIn("fusions, changements de code et millésimes non harmonisés", text)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes()
                                  for p in self.root.rglob("*") if p.is_file()})

    def test_cli_rejects_invalid_region_or_window(self):
        for args in (["--region", "Bretagne"], ["--start-year", "2025", "--end-year", "2020"],
                     ["--max-examples", "0"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    coverage.main(args)
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
