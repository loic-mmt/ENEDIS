import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/module_1/installer_base_locale.py"
spec = importlib.util.spec_from_file_location("local_install", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class LocalInstallTests(unittest.TestCase):
    def test_reference_accepts_exact_file_and_ignores_windows_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"source.csv").write_bytes(b"a,b")
            (root/"source.csv:Zone.Identifier").write_text("metadata")
            ref = {"files":{"source.csv":{"bytes":3,"sha256":hashlib.sha256(b"a,b").hexdigest()}}}
            module.check_files(root,ref)
            (root/"source.csv").write_bytes(b"a,c")
            with self.assertRaises(ValueError):
                module.check_files(root,ref)

    def test_reference_rejects_missing_and_extra_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"extra.csv").write_text("data")
            with self.assertRaises(ValueError):
                module.check_files(root,{"files":{}})
            with self.assertRaises(ValueError):
                module.check_files(root,{"files":{"missing.csv":{}}})
