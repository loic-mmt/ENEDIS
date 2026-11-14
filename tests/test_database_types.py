import unittest
import tempfile
from pathlib import Path
from test_database_files import CaptureDatabase
from enedis.database.client import sql_name
from enedis.database.definitions import CSV_TYPES

class DatabaseTypesTests(unittest.TestCase):
    def test_consumption_defaults_preserve_codes_nulls_and_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            path.write_text("Code Commune;Année;Conso totale (MWh)\n01001;2024;0\n2A004;2025;\n01002;2025;12.345\n", encoding="utf-8")
            result = CaptureDatabase().import_csv(path, "consommation_annuelle", delimiter=";")
            self.assertEqual(result["columns"], {"code_commune":"text","annee":"integer","conso_totale_mwh":"numeric"})
            self.assertEqual(result["rows"], [["01001","2024","0"],["2A004","2025",None],["01002","2025","12.345"]])

    def test_long_names_match_actual_normalization(self):
        key = sql_name("conso_totale_corrigee_de_l_alea_climatique_usages_thermosensibles_mwh")
        self.assertEqual(CSV_TYPES["consommation_annuelle"][key], "numeric")

    def test_solar_date_and_measure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            path.write_text("date_mesure;geocode_commune;valeur\n2024-01-01;01001;1.25\n")
            result = CaptureDatabase().import_csv(path, "solaire_commune", delimiter=";")
            self.assertEqual(result["columns"], {"date_mesure":"date","geocode_commune":"text","valeur":"numeric"})
