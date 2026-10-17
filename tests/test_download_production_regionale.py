import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/download_production_regionale.py"
spec = importlib.util.spec_from_file_location("downloader", SCRIPT)
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)

METADATA = {"id": "test", "dataUpdatedAt": "2026-07-30", "updatedAt": "2026-07-30", "count": 3}
NEXT = downloader.DATASET_URL + "/lines?size=2&after=test"
FIRST = {"total": 3, "results": [{"_id": "a"}, {"_id": "b"}], "next": NEXT}
LAST = {"results": [{"_id": "c"}]}


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)
        self.args = argparse.Namespace(output=self.output, page_size=2, max_pages=1,
                                       timeout=1, retries=0, delay=0)

    def state(self):
        return json.loads((self.output / "checkpoint.json").read_text())

    def first_page(self):
        with patch.object(downloader, "request_json", side_effect=[METADATA, FIRST]):
            downloader.download(self.args)

    def test_resume_uses_saved_cursor_and_checks_final_total(self):
        self.first_page()
        self.assertEqual(self.state()["downloaded"], 2)
        with patch.object(downloader, "request_json", side_effect=[METADATA, LAST, METADATA]) as request:
            downloader.download(self.args)
        self.assertEqual(request.call_args_list[1].args[0], NEXT)
        self.assertTrue(self.state()["complete"])
        self.assertEqual(self.state()["downloaded"], 3)
        self.assertEqual(len(list(self.output.glob("page-*.json.gz"))), 2)

    def test_recovers_page_saved_before_checkpoint_interruption(self):
        real_write = downloader.atomic_json

        def interrupt_checkpoint(path, value, compressed=False):
            if path.name == "checkpoint.json" and value["pages"] == 1:
                raise OSError("simulated interruption")
            real_write(path, value, compressed)

        with patch.object(downloader, "request_json", side_effect=[METADATA, FIRST]), \
                patch.object(downloader, "atomic_json", side_effect=interrupt_checkpoint):
            with self.assertRaises(OSError):
                downloader.download(self.args)
        self.assertEqual(self.state()["downloaded"], 0)
        with patch.object(downloader, "request_json", return_value=METADATA) as request:
            downloader.download(self.args)
        self.assertEqual(request.call_count, 1)  # No re-download of the already saved page.
        self.assertEqual(self.state()["downloaded"], 2)

    def test_incomplete_last_page_does_not_advance_checkpoint(self):
        self.first_page()
        bad_page = {"total": 3, "results": []}
        with patch.object(downloader, "request_json", side_effect=[METADATA, bad_page]):
            with self.assertRaises(ValueError):
                downloader.download(self.args)
        self.assertEqual(self.state()["downloaded"], 2)
        self.assertFalse((self.output / "page-000002.json.gz").exists())

    def test_source_change_blocks_resume(self):
        self.first_page()
        changed = dict(METADATA, dataUpdatedAt="2026-08-01")
        with patch.object(downloader, "request_json", return_value=changed) as request:
            with self.assertRaisesRegex(RuntimeError, "Source modifiée"):
                downloader.download(self.args)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.state()["downloaded"], 2)

    def test_network_retry_keeps_same_request(self):
        with patch.object(downloader, "urlopen", side_effect=[TimeoutError("timeout"), TimeoutError("timeout")]) as request, \
                patch.object(downloader.time, "sleep"):
            with self.assertRaises(TimeoutError):
                downloader.request_json(downloader.DATASET_URL, timeout=1, retries=1)
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
