"""Tests sans serveur pour les noms SQL, les CSV et le catalogue.

À exécuter après installation de l'extra database. Non exécutés lors de la
préparation du package à la demande de l'utilisateur.
"""
from pathlib import Path
import tempfile
import unittest

from enedis.database.client import Database, column_mapping, identifier, sql_name
from enedis.database.catalogue import import_existing_data


class CaptureDatabase(Database):
    def __init__(self):
        self.calls = []

    def _import_rows(self, path, table, mapping, columns, rows, force):
        result = {"table": table, "mapping": mapping, "columns": columns,
                  "rows": list(rows), "force": force}
        self.calls.append(result)
        return result


class DatabaseFileTests(unittest.TestCase):
    def test_names_reject_sql_and_detect_collisions(self):
        with self.assertRaises(ValueError):
            identifier("x; DROP TABLE y")
        with self.assertRaises(ValueError):
            column_mapping(["Année", "Annee"])
        self.assertEqual(sql_name("Code Commune"), "code_commune")
        self.assertLessEqual(len(sql_name("colonne" * 20)), 63)

    def test_csv_preserves_zero_codes_and_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.csv"
            path.write_text("Code Commune;Valeur;Année\n01001;0;2024\n2A004; ;2025\n01002;N/A;2025\n", encoding="utf-8")
            result = CaptureDatabase().import_csv(path, "exemple", delimiter=";")
            self.assertEqual(result["rows"], [["01001", "0", "2024"],
                                              ["2A004", None, "2025"],
                                              ["01002", "N/A", "2025"]])
            self.assertEqual(set(result["columns"].values()), {"text"})

    def test_csv_extra_column_and_explicit_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.csv"
            path.write_text("Annee,Nouveau\n2024,ok\n")
            result = CaptureDatabase().import_csv(path, "exemple", types={"annee": "integer"}, delimiter=",")
            self.assertEqual(result["columns"], {"annee": "integer", "nouveau": "text"})
            with self.assertRaises(ValueError):
                CaptureDatabase().import_csv(path, "exemple", types={"absente": "text"}, delimiter=",")

    def test_malformed_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.csv"
            path.write_text("a,b\n1,2,3\n")
            with self.assertRaises(ValueError):
                CaptureDatabase().import_csv(path, "exemple", delimiter=",")

    def test_catalogue_keeps_charge_groups_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "courbes_de_charge"
            folder.mkdir()
            for name in ["RES2-6-9.csv", "RES2-9-12.csv"]:
                (folder / name).write_text("ID;horodate;valeur\n1;2024-01-01;0\n")
            (folder / "ignored.csv:Zone.Identifier").write_text("metadata")
            result = list(import_existing_data(CaptureDatabase(), tmp))
            self.assertEqual({r["table"] for r in result}, {"charge_res2_6_9", "charge_res2_9_12"})


if __name__ == "__main__":
    unittest.main()
