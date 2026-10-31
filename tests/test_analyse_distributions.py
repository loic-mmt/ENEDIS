import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/analyse_distributions.py"
spec = importlib.util.spec_from_file_location("analyse_distributions", SCRIPT)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source_files(self):
        raw = self.root / "raw"
        (raw / "consommation").mkdir(parents=True)
        (raw / "puissance_photovoltaique").mkdir()
        (raw / "production_regionale").mkdir()
        pd.DataFrame([
            [2024, "22001", "22", "53", "Bretagne", "RES", "RESIDENTIEL", "", 0],
            [2024, "22002", "22", "53", "Bretagne", "RES", "RESIDENTIEL", "", 10],
            [2024, "37001", "37", "24", "Centre-Val de Loire", "RES", "RESIDENTIEL", "", 20],
        ], columns=["Année", "Code Commune", "Code Département", "Code Région", "Nom Région",
                    "CODE CATEGORIE CONSOMMATION", "CODE GRAND SECTEUR", "CODE SECTEUR NAF2",
                    "Conso totale (MWh)"]).to_csv(
            raw / "consommation/consommation-electrique-par-secteur-dactivite-commune.csv", index=False)
        pd.DataFrame([
            ["2024-01-01", "22001", "Photovoltaïque", 0],
            ["2024-01-01", "22002", "Photovoltaïque", 2],
            ["2024-01-01", "22003", "Photovoltaïque", 4],
            ["2024-01-01", "37001", "Photovoltaïque", 30],
            ["2024-01-01", "22001", "Solaire thermique", 300],
        ], columns=["date_mesure", "geocode_commune", "type_installation", "valeur"]).to_csv(
            raw / "puissance_photovoltaique/puissance-solaire-installee-commune.csv", index=False)
        self.production_frame(["2024-03-01T00:00:00Z", "2024-03-01T00:30:00Z"], [0, 2e6]).to_parquet(
            raw / "production_regionale/part-1.parquet", index=False)
        (raw / "production_regionale/metadata.json").write_text('{"not": "parquet"}')
        return raw

    def production_frame(self, times, values):
        return pd.DataFrame({"horodate": pd.to_datetime(times, utc=True),
                             "total_energie_injectee_wh": values, "code_region": "53",
                             "filiere_de_production": "F5 : Solaire",
                             "plage_de_puissance_injection": "P0 : Total toutes puissances"})

    def pv_frame(self):
        return analysis.prepare_measures(pd.DataFrame({
            "commune": ["22001", "22001", "22002", "22003", "22003"],
            "year": [2020, 2021, 2021, 2020, 2021], "category": "PV",
            "raw_value": [0, 4, 100, 5, ""],
        }), ["commune", "year"])

    def test_statistics_keep_zero_exclude_invalid_and_all_duplicate_occurrences(self):
        frame = analysis.prepare_measures(pd.DataFrame({
            "id": [0, 1, 2, 3, 4, 5, 5], "raw_value": [0, 2, "", "inf", -1, 100, 200],
        }), ["id"])
        stats = analysis.describe(frame)
        self.assertEqual(stats["n_valides"], 2)
        self.assertEqual(stats["n_manquantes"], 1)
        self.assertEqual(stats["n_invalides"], 2)
        self.assertEqual(stats["n_lignes_repetees"], 2)
        self.assertEqual(stats["n_zeros"], 1)
        self.assertEqual(stats["mediane"], 1)
        self.assertEqual(stats["iqr"], 1)
        self.assertAlmostEqual(stats["ecart_type"], np.sqrt(2))
        self.assertTrue(np.isnan(stats["asymetrie"]))

    def test_common_sample_and_missing_whole_year_are_not_filled(self):
        frame = self.pv_frame()
        stats = analysis.annual_statistics(frame, [2020, 2021], ["commune"])
        common = stats.loc[stats["echantillon"].eq("commun")].set_index("annee")
        self.assertEqual(common["n_valides"].tolist(), [1, 1])
        self.assertEqual(common["mediane"].tolist(), [0, 4])
        all_2021 = stats.loc[stats["echantillon"].eq("disponible") & stats["annee"].eq(2021)].iloc[0]
        self.assertEqual(all_2021["mediane"], 52)
        missing = analysis.annual_statistics(frame, [2020, 2021, 2022], ["commune"])
        self.assertTrue(missing.loc[missing["annee"].eq(2022), "mediane"].isna().all())
        self.assertEqual(missing.loc[missing["echantillon"].eq("commun"), "n_valides"].sum(), 0)

    def test_consumption_common_sample_keeps_same_sector_keys_without_aggregation(self):
        frame = analysis.prepare_measures(pd.DataFrame({
            "commune": ["22001"] * 6, "year": [2020, 2021, 2020, 2021, 2020, 2021],
            "category": ["RES", "RES", "ENT", "ENT", "ENT", "ENT"],
            "sector": ["RES", "RES", "TERTIAIRE", "TERTIAIRE", "INDUSTRIE", "INDUSTRIE"],
            "naf": ["", "", "", "47", "", "24"], "raw_value": [5, 6, 10, 20, 30, 40],
        }), analysis.C_KEYS + ["year"])
        common = analysis.common_sample(frame, analysis.C_KEYS, [2020, 2021])
        self.assertEqual(common["category"].tolist(), ["RES", "RES"])
        self.assertEqual(common["value"].tolist(), [5, 6])
        stats = analysis.annual_statistics(frame, [2020, 2021], analysis.C_KEYS)
        ent = stats.loc[stats["echantillon"].eq("disponible") & stats["categorie"].eq("ENT")]
        self.assertEqual(ent["n_valides"].tolist(), [2, 2])
        self.assertEqual(ent["maximum"].tolist(), [30, 40])

    def test_loaders_use_region_and_keep_pv_communes_absent_from_consumption(self):
        raw = self.source_files()
        c_path = raw / "consommation/consommation-electrique-par-secteur-dactivite-commune.csv"
        pv_path = raw / "puissance_photovoltaique/puissance-solaire-installee-commune.csv"
        c, deps, name, _ = analysis.read_consumption(c_path, "53", 2024, 2024, 1)
        pv, _ = analysis.read_pv(pv_path, deps, 2024, 2024, 1)
        self.assertEqual(name, "Bretagne")
        self.assertEqual(set(pv["commune"]), {"22001", "22002", "22003"})
        self.assertEqual(pv["value"].tolist(), [0, 2, 4])
        _, deps, _, _ = analysis.read_consumption(c_path, "24", 2024, 2024, 1)
        other, _ = analysis.read_pv(pv_path, deps, 2024, 2024, 1)
        self.assertEqual(other["commune"].tolist(), ["37001"])

    def test_production_dst_duplicates_across_files_missing_and_unit_conversion(self):
        path = self.root / "production"
        path.mkdir()
        times = pd.date_range("2024-03-01", "2024-04-01", freq="30min", inclusive="left", tz="Europe/Paris")
        source = self.production_frame(times, [1e6] * len(times))
        source.loc[1, "total_energie_injectee_wh"] = np.nan
        source.loc[2, "total_energie_injectee_wh"] = 0
        other = source.iloc[:1].assign(filiere_de_production="F0 : Total toutes filières")
        pd.concat([source, other]).to_parquet(path / "a.parquet", index=False)
        source.iloc[:1].to_parquet(path / "b.parquet", index=False)
        (path / "metadata.json").write_text('{}')
        frame, expected, _ = analysis.read_production(path, "53", None, None, 113)
        month = analysis.production_statistics(frame, expected, ["mois"]).iloc[0]
        self.assertEqual(month["n_attendues"], 31 * 48 - 2)
        self.assertEqual(month["n_presentes"], len(times))
        self.assertEqual(month["n_valides"], len(times) - 2)
        self.assertEqual(month["n_manquantes"], 1)
        self.assertEqual(month["n_lignes_repetees"], 2)
        self.assertEqual(month["n_zeros"], 1)
        self.assertEqual(month["mediane"], 1)  # MWh par demi-heure, pas Wh ni MW.
        self.assertFalse(month["complet"])
        self.assertTrue(np.isnan(month["total_complet_mwh"]))

    def test_absent_month_and_repeated_local_hour_keep_correct_calendar(self):
        path = self.root / "production"
        path.mkdir()
        self.production_frame(["2024-01-02T00:00:00Z", "2024-03-02T00:00:00Z"], [0, 1e6]).to_parquet(
            path / "a.parquet", index=False)
        frame, expected, _ = analysis.read_production(path, "53", None, None, 2)
        months = analysis.production_statistics(frame, expected, ["mois"]).set_index("mois")
        feb = months.loc["2024-02"]
        self.assertEqual(feb["n_attendues"], 29 * 48)
        self.assertEqual(feb["n_valides"], 0)
        self.assertTrue(np.isnan(feb["mediane"]))
        self.assertTrue(np.isnan(feb["somme_connue_mwh"]))
        self.production_frame(["2024-10-27T00:00:00Z", "2024-10-27T01:00:00Z"], [1e6, 2e6]).to_parquet(
            path / "a.parquet", index=False)
        frame, expected, _ = analysis.read_production(path, "53", None, None, 1)
        self.assertEqual(frame["heure"].tolist(), [2, 2])
        self.assertTrue(frame["usable"].all())
        hour = analysis.production_statistics(frame, expected, ["mois", "heure"]).set_index(["mois", "heure"])
        self.assertEqual(hour.loc[("2024-10", 2), "n_attendues"], 31 * 2 + 2)
        self.assertEqual(hour.loc[("2024-10", 2), "n_valides"], 2)

    def test_complete_month_can_have_a_real_zero_total(self):
        path = self.root / "production"
        path.mkdir()
        times = pd.date_range("2024-02-01", "2024-03-01", freq="30min", inclusive="left", tz="Europe/Paris")
        self.production_frame(times, [0.] * len(times)).to_parquet(path / "a.parquet", index=False)
        frame, expected, _ = analysis.read_production(path, "53", None, None, 400)
        month = analysis.production_statistics(frame, expected, ["mois"]).iloc[0]
        self.assertTrue(month["complet"])
        self.assertEqual(month["total_complet_mwh"], 0)
        self.assertEqual(month["couverture_pct"], 100)

    def test_three_cli_analyses_create_csv_and_plots_without_changing_raw(self):
        raw = self.source_files()
        before = {p.relative_to(raw): p.read_bytes() for p in raw.rglob("*") if p.is_file()}
        for mode in ["pv", "consommation", "production"]:
            with self.subTest(mode=mode):
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    status = analysis.main([mode, "--data-dir", str(raw), "--output-dir", str(self.root / "reports"),
                                            "--start-year", "2024", "--end-year", "2024", "--chunksize", "1"])
                self.assertEqual(status, 0, errors.getvalue())
                directory = self.root / f"reports/region_53/{mode}"
                self.assertGreaterEqual(len(list(directory.rglob("*.csv"))), 2)
                images = list(directory.rglob("*.png"))
                self.assertTrue(images)
                for image in images:
                    self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(before, {p.relative_to(raw): p.read_bytes() for p in raw.rglob("*") if p.is_file()})

    def test_production_cli_does_not_require_other_source_files(self):
        raw = self.root / "raw"
        path = raw / "production_regionale"
        path.mkdir(parents=True)
        self.production_frame(["2024-01-01T00:00:00Z"], [0]).to_parquet(path / "a.parquet", index=False)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            status = analysis.main(["production", "--data-dir", str(raw), "--output-dir", str(self.root / "reports"),
                                    "--no-plots"])
        self.assertEqual(status, 0)

    def test_cli_rejects_invalid_options(self):
        for argv in [["pv", "--bins", "0"], ["production", "--start-year", "2025", "--end-year", "2024"],
                     ["pv", "--region", "Bretagne"]]:
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    analysis.main(argv)
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
