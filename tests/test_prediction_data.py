import importlib.util
from pathlib import Path
import tempfile
import unittest

import pandas as pd


SOURCE = Path(__file__).resolve().parents[1] / "src/enedis/prediction/data.py"
spec = importlib.util.spec_from_file_location("prediction_data", SOURCE)
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)


class PredictionDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.frame = pd.DataFrame({"value": [10.0, 20.0], "year": [2024, 2025]})

    def test_csv(self):
        path = self.root / "sample.CSV"
        self.frame.to_csv(path, index=False)
        pd.testing.assert_frame_equal(data.load_all_data(path), self.frame)

    def test_parquet_file(self):
        path = self.root / "sample.parquet"
        self.frame.to_parquet(path, index=False)
        pd.testing.assert_frame_equal(data.load_all_data(path), self.frame)

    def test_partitioned_directory_and_year_filter(self):
        path = self.root / "dataset"
        self.frame.to_parquet(path, partition_cols=["year"], index=False)
        self.assertEqual(len(data.load_all_data(path)), 2)
        selected = data.load_filtered_data(path, 2025)
        self.assertIsInstance(selected, pd.DataFrame)
        self.assertEqual(selected["value"].tolist(), [20.0])
        self.assertEqual(selected["year"].tolist(), [2025])
        empty = data.load_filtered_data(path, 2030)
        self.assertTrue(empty.empty)
        self.assertEqual(list(empty.columns), list(selected.columns))

    def test_directory_without_parquet(self):
        with self.assertRaisesRegex(ValueError, "Aucun fichier Parquet"):
            data.load_all_data(self.root)

    def test_unsupported_format(self):
        path = self.root / "sample.txt"
        path.write_text("test")
        with self.assertRaisesRegex(ValueError, "Format non pris en charge"):
            data.load_all_data(path)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            data.load_all_data(self.root / "missing.csv")

    def test_filter_requires_year_field(self):
        path = self.root / "sample.parquet"
        self.frame.drop(columns="year").to_parquet(path, index=False)
        with self.assertRaisesRegex(ValueError, "champ year"):
            data.load_filtered_data(path, 2025)


if __name__ == "__main__":
    unittest.main()
