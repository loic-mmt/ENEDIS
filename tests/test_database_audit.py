import importlib.util
from pathlib import Path
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/"scripts/module_1/auditer_imports.py"
spec=importlib.util.spec_from_file_location("audit",path)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class AuditTests(unittest.TestCase):
    def test_multiline_csv_counts_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            f=root/"example.csv"
            f.write_text('a;b\n1;"hello\nworld"\n2;ok\n')
            table,name,count,sha=audit.source_info(f,root)
            self.assertEqual(count,2)
            self.assertEqual(table,"example")
            self.assertEqual(len(sha),64)

    def test_json_document_is_one_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            f=root/"meta.json"
            f.write_text('[1,2,3]')
            self.assertEqual(audit.source_info(f,root)[0:3:2],("documents_source",1))
