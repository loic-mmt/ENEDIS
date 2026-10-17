import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pyarrow.dataset as ds

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from convert_production_regionale_parquet import convert


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "raw"
        self.source.mkdir()
        self.output = Path(self.directory.name) / "parquet"
        self.metadata = {"count": 4, "schema": [
            {"key": "horodate", "type": "string"},
            {"key": "code_region", "type": "string"},
            {"key": "valeur", "type": "number"},
            {"key": "indice", "type": "string"},
            {"key": "_id", "type": "string"},
        ]}
        self.checkpoint = {"complete": True, "next": None, "downloaded": 4,
                           "total": 4, "pages": 2, "revision": {"id": "test"}}
        self.write_json("metadata.json", self.metadata)
        self.write_json("checkpoint.json", self.checkpoint)
        self.next = "https://opendata.enedis.fr/data-fair/api/v1/datasets/test/lines?after=2"
        self.write_page(1, "https://opendata.enedis.fr/first", self.next, [
            {"_id": "a", "horodate": "2024-12-31T23:30:00+01:00", "code_region": "01", "valeur": None, "indice": "S"},
            {"_id": "b", "horodate": "2025-01-01T00:00:00+01:00", "code_region": "01", "valeur": 2.5, "indice": "50"},
        ])
        self.write_page(2, self.next, None, [
            {"_id": "c", "horodate": "2025-07-01T00:00:00+02:00", "code_region": "11", "valeur": 0, "indice": "S"},
            {"_id": "d", "horodate": "2025-12-31T23:30:00+01:00", "code_region": "11", "valeur": 3, "indice": "100"},
        ])

    def write_json(self, name, value):
        (self.source / name).write_text(json.dumps(value))

    def write_page(self, number, url, next_url, rows):
        with gzip.open(self.source / f"page-{number:06d}.json.gz", "wt") as stream:
            json.dump({"request_url": url, "response": {"results": rows, "next": next_url}}, stream)

    def test_local_year_partition_roundtrip_and_file_rotation(self):
        report = convert(self.source, self.output, batch_pages=1, rows_per_file=2)
        self.assertEqual(report["rows_by_year"], {"2024": 1, "2025": 3})
        self.assertEqual(report["files"], 3)
        table = ds.dataset(self.output, format="parquet", partitioning="hive").to_table()
        rows = {r["_id"]: r for r in table.to_pylist()}
        self.assertEqual(rows["b"]["year"], 2025)  # UTC date is still in 2024.
        self.assertEqual(rows["b"]["horodate"].year, 2024)
        self.assertEqual(rows["a"]["code_region"], "01")
        self.assertIsNone(rows["a"]["valeur"])
        self.assertEqual(rows["a"]["indice"], "S")
        self.assertEqual(rows["c"]["valeur"], 0)
        self.assertEqual(rows["c"]["horodate_source"], "2025-07-01T00:00:00+02:00")
        self.assertTrue((self.source / "page-000001.json.gz").exists())

    def test_incomplete_source_not_published(self):
        self.checkpoint["complete"] = False
        self.write_json("checkpoint.json", self.checkpoint)
        with self.assertRaisesRegex(ValueError, "incomplet"):
            convert(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_page_rejected_before_conversion(self):
        (self.source / "page-000002.json.gz").unlink()
        with self.assertRaisesRegex(ValueError, "pages incohérente"):
            convert(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_broken_cursor_never_publishes_dataset(self):
        with gzip.open(self.source / "page-000002.json.gz", "rt") as stream:
            page = json.load(stream)
        self.write_page(2, "https://opendata.enedis.fr/wrong", None, page["response"]["results"])
        with self.assertRaisesRegex(ValueError, "pagination rompue"):
            convert(self.source, self.output, batch_pages=1)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
