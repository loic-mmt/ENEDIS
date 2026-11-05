from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from enedis.prediction.imputation_evaluation import ENERGY, SITES, prepare_evaluation

SPEC = importlib.util.spec_from_file_location("impute_data_script", ROOT / "scripts/module_2/impute_data.py")
SCRIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRIPT)


class ImputeDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        raw = self.root / "raw/production_regionale"
        raw.mkdir(parents=True)
        index = pd.date_range("2024-01-01", "2024-07-01", freq="30min", inclusive="left", tz="UTC")
        frame = pd.DataFrame({"horodate": index, ENERGY: 1e6, SITES: 100., "code_region": "53",
                              "filiere_de_production": "F5 : Solaire",
                              "plage_de_puissance_injection": "P0 : Total toutes puissances"})
        frame.loc[100:101, ENERGY] = np.nan
        frame.to_parquet(raw / "part.parquet", index=False)
        self.evaluation = prepare_evaluation(self.root / "raw", self.root / "imputed", gaps_per_split=2)
        self.args = ["--evaluation-dir", str(self.evaluation), "--latitude", "48", "--longitude", "-3",
                     "--size", "small", "--num-estimators", "1", "--context-size", "16", "--device", "cpu"]

    def call(self, arguments=None):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = SCRIPT.main(self.args if arguments is None else arguments)
        return code, output.getvalue(), errors.getvalue()

    def runs(self):
        region = self.evaluation.parent.parent
        return sorted((region / "runs" / self.evaluation.name).glob("kumo_forward_*/*/manifest.json"))

    def test_validation_exports_metrics_progress_cache_and_preserves_inputs(self):
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                  for path in self.root.rglob("*") if path.is_file()}
        with patch.object(SCRIPT, "KumoTabularRegressor", return_value=DummyRegressor()) as constructor:
            code, output, errors = self.call()
            self.assertEqual((code, errors), (0, ""))
            self.assertIn("[1/2]", output)
            self.assertIn("[2/2]", output)
            self.assertIn("mae_mwh", output)
            constructor.assert_called_once_with(size="small", device="cpu", num_estimators=1,
                                                batch_size=256, random_state=42, context_size=None)
            directory = self.runs()[0].parent
            manifest = json.loads((directory / "manifest.json").read_text())
            self.assertEqual(manifest["split"], "validation")
            self.assertEqual(manifest["direction"], "forward")
            self.assertEqual(manifest["groups"], ["A", "B", "C"])
            self.assertEqual(manifest["prediction_clip_min"], 0.)
            self.assertEqual(manifest["lag_basis"], "utc")
            self.assertEqual(directory.parent.name, "kumo_forward_abc")
            self.assertEqual(manifest["n_gaps"], 2)
            self.assertEqual(manifest["n_targets"], 4)
            self.assertEqual((directory / manifest["evaluation_relative_path"]).resolve(), self.evaluation)
            for name in ("predictions.parquet", "diagnostics.parquet", "scores.parquet",
                         "scores_global.csv", "scores_stratified.csv", "manifest.json"):
                self.assertTrue((directory / name).is_file(), name)
            predictions = pd.read_parquet(directory / "predictions.parquet")
            self.assertTrue(predictions.gap_id.str.startswith("validation_").all())
            self.assertNotIn("true_value_wh", predictions)
            self.assertTrue(predictions.prediction_wh.eq(1e6).all())
            diagnostics = pd.read_parquet(directory / "diagnostics.parquet")
            self.assertTrue(diagnostics.n_context.eq(16).all())
            scores = pd.read_parquet(directory / "scores.parquet")
            overall = scores.loc[scores.scope.eq("all_targets") & scores.stratum.eq("overall")].iloc[0]
            self.assertEqual(overall.mae_mwh, 0.)
            self.assertEqual(overall.coverage, 1.)
            self.assertEqual(set(scores.loc[scores.stratum.eq("light"), "stratum_value"]), {"day", "night"})

            cache = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in directory.iterdir()}
            code, output, errors = self.call()
            self.assertEqual((code, errors), (0, ""))
            self.assertIn("aucun nouveau fit", output)
            self.assertEqual(constructor.call_count, 1)
            self.assertEqual(cache, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in directory.iterdir()})
        for path, content in before.items():
            self.assertEqual(content, (path.read_bytes(), path.stat().st_mtime_ns))

    def test_limited_trial_keeps_all_masks_and_scores_only_selected_targets(self):
        reconstruct = SCRIPT.reconstruct_with_model
        with patch.object(SCRIPT, "KumoTabularRegressor", return_value=DummyRegressor()), \
             patch.object(SCRIPT, "reconstruct_with_model", wraps=reconstruct) as runner:
            code, output, errors = self.call(self.args + ["--max-gaps", "1"])
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("Essai limité", output)
        masked_inputs, gaps = runner.call_args.args[:2]
        self.assertEqual(len(gaps), 1)
        all_masks = pd.read_parquet(self.evaluation / "masks.parquet")
        within_phase = all_masks.index.intersection(masked_inputs.index)
        self.assertTrue(masked_inputs.loc[within_phase, ENERGY].isna().all())
        self.assertFalse(masked_inputs.loc[within_phase, "is_observed"].any())
        directory = self.runs()[0].parent
        manifest = json.loads((directory / "manifest.json").read_text())
        self.assertEqual(manifest["n_gaps"], 1)
        self.assertEqual(manifest["n_validation_gaps"], 2)
        self.assertEqual(manifest["n_targets"], 2)
        self.assertEqual(len(pd.read_parquet(directory / "predictions.parquet")), 2)

    def test_clipped_predictions_are_scored_and_raw_predictions_are_exported(self):
        with patch.object(SCRIPT, "KumoTabularRegressor", return_value=DummyRegressor(strategy="constant", constant=-1.)):
            code, output, errors = self.call()
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("4 prédictions négatives", output)
        directory = self.runs()[0].parent
        predictions = pd.read_parquet(directory / "predictions.parquet")
        self.assertTrue(predictions.prediction_raw_wh.eq(-1.).all())
        self.assertTrue(predictions.prediction_wh.eq(0.).all())
        scores = pd.read_parquet(directory / "scores.parquet")
        overall = scores.loc[scores.scope.eq("all_targets") & scores.stratum.eq("overall")].iloc[0]
        self.assertEqual(overall.mae_mwh, 1.)

    def test_ab_comparison_uses_same_masks_and_a_separate_result_directory(self):
        with patch.object(SCRIPT, "KumoTabularRegressor", side_effect=lambda **kwargs: DummyRegressor()):
            self.assertEqual(self.call()[0], 0)
            self.assertEqual(self.call(self.args + ["--groups", "A", "B"])[0], 0)
        self.assertEqual(len(self.runs()), 2)
        manifests = [json.loads(path.read_text()) for path in self.runs()]
        self.assertEqual(manifests[0]["gap_ids"], manifests[1]["gap_ids"])
        self.assertEqual({path.parent.parent.name for path in self.runs()}, {"kumo_forward_ab", "kumo_forward_abc"})

    def test_model_seed_changes_run_without_changing_masks(self):
        before_masks = (self.evaluation / "masks.parquet").read_bytes()
        with patch.object(SCRIPT, "KumoTabularRegressor", side_effect=lambda **kwargs: DummyRegressor()) as constructor:
            self.assertEqual(self.call()[0], 0)
            self.assertEqual(self.call(self.args + ["--model-seed", "7"])[0], 0)
        self.assertEqual(constructor.call_count, 2)
        self.assertEqual(len(self.runs()), 2)
        self.assertEqual(before_masks, (self.evaluation / "masks.parquet").read_bytes())
        manifests = [json.loads(path.read_text()) for path in self.runs()]
        self.assertEqual(manifests[0]["gap_ids"], manifests[1]["gap_ids"])
        self.assertEqual({manifest["model_options"]["random_state"] for manifest in manifests}, {7, 42})

    def test_corrupted_output_is_rejected_without_rerun_or_overwrite(self):
        with patch.object(SCRIPT, "KumoTabularRegressor", return_value=DummyRegressor()) as constructor:
            self.assertEqual(self.call()[0], 0)
            prediction_path = self.runs()[0].parent / "predictions.parquet"
            prediction_path.write_bytes(b"changed")
            code, _, errors = self.call()
        self.assertEqual(code, 1)
        self.assertIn("modifié", errors)
        self.assertEqual(constructor.call_count, 1)
        self.assertEqual(prediction_path.read_bytes(), b"changed")

    def test_missing_sdk_reports_error_without_partial_export(self):
        with patch.object(SCRIPT, "KumoTabularRegressor", side_effect=ImportError("requirements-kumo.txt")):
            code, _, errors = self.call()
        self.assertEqual(code, 1)
        self.assertIn("requirements-kumo.txt", errors)
        self.assertEqual(self.runs(), [])

    def test_raw_symlink_destination_rejected_before_model_creation(self):
        (self.evaluation.parent.parent / "runs").symlink_to(self.root / "raw", target_is_directory=True)
        with patch.object(SCRIPT, "KumoTabularRegressor") as constructor:
            code, _, errors = self.call()
        self.assertEqual(code, 1)
        self.assertIn("raw", errors)
        constructor.assert_not_called()

    def test_invalid_parameters_fail_before_reading_data(self):
        for arguments in (["--context-size", "1"], ["--max-gaps", "0"], ["--latitude", "91"],
                          ["--context-size", "2", "--min-observations", "3"]):
            with self.subTest(arguments=arguments), patch.object(SCRIPT, "_run") as run:
                code, _, errors = self.call(self.args + arguments)
                self.assertEqual(code, 1)
                self.assertIn("Échec", errors)
                run.assert_not_called()

    def test_default_preparation_finds_same_evaluation(self):
        arguments = ["--data-dir", str(self.root / "raw"), "--output-dir", str(self.root / "imputed"),
                     "--gaps-per-split", "2", "--latitude", "48", "--longitude", "-3", "--context-size", "16"]
        with patch.object(SCRIPT, "KumoTabularRegressor", return_value=DummyRegressor()):
            code, _, errors = self.call(arguments)
        self.assertEqual((code, errors), (0, ""))
        manifest = json.loads(self.runs()[0].read_text())
        self.assertEqual(manifest["evaluation_id"], self.evaluation.name)


if __name__ == "__main__":
    unittest.main()
