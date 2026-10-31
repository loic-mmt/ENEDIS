import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/coverage_region_pilote.py"
spec = importlib.util.spec_from_file_location("coverage_region_pilote", SCRIPT)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def consumption(self):
        path = self.root / "consumption.csv"
        pd.DataFrame({
            "Année": [2020, 2021, 2020, 2020, 2021],
            "Code Commune": ["44001", "44001", "44001", "84001", "84001"],
            "Code Région": ["44", "44", "44", "84", "84"],
            "CODE CATEGORIE CONSOMMATION": ["RES", "RES", "PRO", "RES", "RES"],
            "Conso totale (MWh)": [0., 10., np.nan, 5., 6.],
        }).to_csv(path, index=False)
        return path

    def pv(self):
        path = self.root / "pv.csv"
        pd.DataFrame({
            "date_mesure": ["2020-01-01", "2021-01-01", "2020-01-01", "2021-01-01", "1900-01-01"],
            "geocode_region": ["44", "44", "84", "84", "44"],
            "type_installation": ["Photovoltaïque"] * 5,
            "valeur": [0., 1., 2., 3., 1.],
        }).to_csv(path, index=False)
        return path

    def production(self):
        path = self.root / "production"
        path.mkdir()
        times = pd.date_range("2024-03-01", "2024-04-01", freq="30min",
                              inclusive="left", tz="Europe/Paris").tz_convert("UTC")
        frame = pd.DataFrame({
            "horodate": times, "code_region": "44",
            "filiere_de_production": "F5 : Solaire",
            "plage_de_puissance_injection": "P0 : Total toutes puissances",
            "total_energie_injectee_wh": 0.,
        })
        # Include a total row that must never be counted in the solar selection.
        other = frame.iloc[:1].assign(filiere_de_production="F0 : Total toutes filières")
        pd.concat([frame, other]).to_parquet(path / "part-1.parquet", index=False)
        (path / "metadata.json").write_text('{"not": "parquet"}')
        return path, len(frame)

    def test_consumption_missing_across_chunks_and_zero_preserved(self):
        annual, communes, _ = coverage.read_consumption(self.consumption(), 2020, 2021, 1)
        self.assertEqual(annual[("44", 2020)]["rows"], 2)
        self.assertEqual(annual[("44", 2020)]["known"], 1)
        self.assertEqual(annual[("44", 2020)]["all_published_known"], 0)
        self.assertEqual(annual[("44", 2020)]["res_all_published_known"], 1)
        present, incomplete, _, _ = communes[("44", "44001")]
        self.assertEqual((present & ~incomplete).bit_count(), 1)

    def test_duplicate_pv_year_not_counted_as_usable(self):
        path = self.pv()
        frame = pd.read_csv(path, dtype=str)
        pd.concat([frame, frame.iloc[:1]]).to_csv(path, index=False)
        annual, diag = coverage.read_pv(path, 2020, 2021)
        self.assertFalse(annual[("44", 2020)]["usable"])
        self.assertTrue(annual[("44", 2021)]["usable"])
        self.assertEqual(diag["outside_window_or_regions"], 1)

    def test_calendar_handles_daylight_saving_and_absent_regions(self):
        path, length = self.production()
        monthly, calendar, diag = coverage.read_production(path, 113)
        self.assertEqual(calendar, ["2024-03"])
        self.assertEqual(length, 31 * 48 - 2)
        self.assertEqual(coverage.expected_slots("2024-03"), length)
        self.assertEqual(coverage.expected_slots("2024-10"), 31 * 48 + 2)
        self.assertEqual(diag["rows"], length)
        self.assertTrue(monthly[("44", "2024-03")]["complete"])
        self.assertEqual(len(monthly[("84", "2024-03")]["valid"]), 0)
        self.assertEqual(monthly[("84", "2024-03")]["expected"], length)

    def test_duplicate_production_and_missing_energy_reduce_coverage(self):
        path, length = self.production()
        frame = pd.read_parquet(path / "part-1.parquet")
        frame.loc[1, "total_energie_injectee_wh"] = np.nan
        frame.to_parquet(path / "part-1.parquet", index=False)
        frame.iloc[:1].to_parquet(path / "part-2.parquet", index=False)
        monthly, _, _ = coverage.read_production(path, 113)
        month = monthly[("44", "2024-03")]
        self.assertEqual(len(month["seen"]), length)
        self.assertEqual(len(month["valid"]), length - 2)
        self.assertEqual(len(month["duplicates"]), 1)
        self.assertFalse(month["complete"])

    def test_missing_calendar_month_is_not_hidden(self):
        path, _ = self.production()
        frame = pd.read_parquet(path / "part-1.parquet").iloc[:1].copy()
        frame["horodate"] = pd.to_datetime(["2024-05-01T00:00:00Z"])
        frame.to_parquet(path / "part-2.parquet", index=False)
        monthly, calendar, _ = coverage.read_production(path, 2000)
        self.assertIn("2024-04", calendar)
        self.assertEqual(len(monthly[("44", "2024-04")]["seen"]), 0)
        self.assertEqual(monthly[("44", "2024-04")]["expected"], 30 * 48)

    def test_ranking_and_terminal_report_do_not_write_data(self):
        c, communes, c_diag = coverage.read_consumption(self.consumption(), 2020, 2021, 2)
        pv, pv_diag = coverage.read_pv(self.pv(), 2020, 2021)
        path, _ = self.production()
        p, calendar, p_diag = coverage.read_production(path, 2000)
        ranking = coverage.rank_regions(c, communes, pv, p, calendar, 2020, 2021, 2)
        self.assertEqual(ranking[0]["region"], "44")
        self.assertAlmostEqual(ranking[0]["consumption"], 2 / 3)
        before = {file: file.read_bytes() for file in self.root.rglob("*") if file.is_file()}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            coverage.print_report(ranking, c, pv, p, calendar,
                                  {"C": c_diag, "PV": pv_diag, "P": p_diag},
                                  2020, 2021, 2, details="pilot")
        text = output.getvalue()
        self.assertIn("RÉGION PILOTE SUGGÉRÉE", text)
        self.assertIn("Grand Est", text)
        self.assertIn("provisoire", text)
        self.assertEqual(before, {file: file.read_bytes() for file in self.root.rglob("*") if file.is_file()})

    def test_absent_production_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Aucun Parquet"):
            coverage.read_production(self.root, 100)

    def test_no_complete_month_warning_is_explicit(self):
        c, communes, c_diag = coverage.read_consumption(self.consumption(), 2020, 2021, 2)
        pv, pv_diag = coverage.read_pv(self.pv(), 2020, 2021)
        path, _ = self.production()
        frame = pd.read_parquet(path / "part-1.parquet")
        frame.loc[0, "total_energie_injectee_wh"] = np.nan
        frame.to_parquet(path / "part-1.parquet", index=False)
        p, calendar, p_diag = coverage.read_production(path, 2000)
        ranking = coverage.rank_regions(c, communes, pv, p, calendar, 2020, 2021, 2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            coverage.print_report(ranking, c, pv, p, calendar,
                                  {"C": c_diag, "PV": pv_diag, "P": p_diag},
                                  2020, 2021, 2, details="none")
        self.assertIn("aucun mois de production entièrement renseigné", output.getvalue())


if __name__ == "__main__":
    unittest.main()
