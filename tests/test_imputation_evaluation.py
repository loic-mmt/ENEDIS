import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.imputation_evaluation import (
    ENERGY, SITES, SPLITS, STEP, evaluation_periods, load_evaluation_split,
    prepare_evaluation, read_solar_series, score_reconstruction,
)


class ImputationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.output = self.root / "imputed"
        self.production = self.raw / "production_regionale"
        self.production.mkdir(parents=True)
        times = pd.date_range("2024-01-01", "2025-01-01", freq="30min", inclusive="left", tz="UTC")
        source = pd.DataFrame({"horodate": times, ENERGY: np.arange(len(times), dtype=float),
                               SITES: 100., "code_region": "53", "filiere_de_production": "F5 : Solaire",
                               "plage_de_puissance_injection": "P0 : Total toutes puissances"})
        for date, length, hide_sites in [("2024-03-14T12:00Z", 1, True), ("2024-07-14T12:00Z", 2, False),
                                         ("2024-10-14T12:00Z", 3, True)]:
            first = int(times.get_loc(pd.Timestamp(date)))
            source.loc[first:first + length - 1, ENERGY] = np.nan
            if hide_sites:
                source.loc[first:first + length - 1, SITES] = np.nan
        # Other categories sharing timestamps must not enter the regional F5/P0 series.
        other = source.iloc[:2].assign(filiere_de_production="F0 : Total toutes filières")
        pd.concat([source.iloc[::2], other]).to_parquet(self.production / "a.parquet", index=False)
        source.iloc[1::2].to_parquet(self.production / "b.parquet", index=False)
        (self.production / "metadata.json").write_text('{"not": "parquet"}')

    def prepare(self, **kwargs):
        return prepare_evaluation(self.raw, self.output, gaps_per_split=3, **kwargs)

    def manifests(self, evaluation):
        manifest = json.loads((evaluation / "manifest.json").read_text())
        snapshot = (evaluation / manifest["base_relative_path"]).resolve()
        return manifest, snapshot

    def test_arrow_reads_only_filtered_observations_and_regularizes_missing_rows(self):
        files = sorted(self.production.glob("*.parquet"))
        base = read_solar_series(files, "53", batch_size=113)
        self.assertEqual(len(base), 366 * 48)
        self.assertEqual(int((~base["is_observed"]).sum()), 6)
        self.assertEqual(int(base[SITES].isna().sum()), 4)
        self.assertEqual(base.iloc[0][ENERGY], 0)
        self.assertTrue(base["source_present"].all())
        source = pd.read_parquet(files[0])
        removed = pd.Timestamp("2024-06-01T00:00Z")
        source.loc[~source["horodate"].eq(removed)].to_parquet(files[0], index=False)
        base = read_solar_series(files, "53", batch_size=113)
        self.assertFalse(base.loc[removed, "source_present"])
        self.assertTrue(pd.isna(base.loc[removed, ENERGY]))

    def test_reproducibility_cache_shared_base_and_raw_preserved(self):
        before = {p.relative_to(self.raw): p.read_bytes() for p in self.raw.rglob("*") if p.is_file()}
        evaluation = self.prepare(seed=42)
        snapshot = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.output.rglob("*") if p.is_file()}
        self.assertEqual(self.prepare(seed=42), evaluation)
        self.assertEqual(snapshot, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                   for p in self.output.rglob("*") if p.is_file()})
        other = self.prepare(seed=43)
        self.assertNotEqual(evaluation, other)
        _, base_a = self.manifests(evaluation)
        _, base_b = self.manifests(other)
        self.assertEqual(base_a, base_b)
        self.assertEqual(before, {p.relative_to(self.raw): p.read_bytes()
                                  for p in self.raw.rglob("*") if p.is_file()})

    def test_complete_blocks_known_neighbors_no_overlap_and_real_lengths(self):
        evaluation = self.prepare()
        manifest, snapshot = self.manifests(evaluation)
        base = pd.read_parquet(snapshot / "observations.parquet")
        cases = pd.read_parquet(evaluation / "gaps.parquet")
        masks = pd.read_parquet(evaluation / "masks.parquet")
        self.assertEqual(len(cases), 9)
        self.assertTrue(masks.index.is_unique)
        for split in SPLITS:
            self.assertEqual(set(cases.loc[cases["split"].eq(split), "n_slots"]), {1, 2, 3})
        for _, gap in cases.iterrows():
            points = masks.loc[masks["gap_id"].eq(gap["gap_id"])]
            expected = pd.date_range(gap["start"], gap["end_exclusive"], freq="30min", inclusive="left")
            self.assertEqual(points.index.tolist(), expected.tolist())
            self.assertTrue(base.loc[points.index, "is_observed"].all())
            for neighbor in (gap["start"] - STEP, gap["end_exclusive"]):
                self.assertTrue(base.loc[neighbor, "is_observed"])
                self.assertNotIn(neighbor, masks.index)
            self.assertLess(gap["end_exclusive"], pd.Timestamp(manifest["periods"][gap["split"]]["end_exclusive"]))
        self.assertTrue(cases["duration_weight"].gt(0).all())

    def test_loader_masks_all_cases_before_features_and_separates_truth(self):
        evaluation = self.prepare()
        manifest, snapshot = self.manifests(evaluation)
        base = pd.read_parquet(snapshot / "observations.parquet")
        masks = pd.read_parquet(evaluation / "masks.parquet")
        for split in SPLITS:
            inputs, truth, cases = load_evaluation_split(evaluation, split)
            cutoff = pd.Timestamp(manifest["periods"][split]["end_exclusive"])
            self.assertTrue((inputs.index < cutoff).all())
            all_hidden = masks.loc[masks.index < cutoff]
            self.assertTrue(inputs.loc[all_hidden.index, ENERGY].isna().all())
            self.assertFalse(inputs.loc[all_hidden.index, "is_observed"].any())
            self.assertTrue(truth["true_value_wh"].notna().all())
            np.testing.assert_array_equal(truth["true_value_wh"], base.loc[truth.index, ENERGY])
            self.assertTrue(truth["split"].eq(split).all())
            self.assertEqual(set(truth["gap_id"]), set(cases["gap_id"]))
            self.assertTrue(inputs.loc[all_hidden.index[all_hidden["mask_sites"]], SITES].isna().all())
            kept = all_hidden.index[~all_hidden["mask_sites"]]
            np.testing.assert_array_equal(inputs.loc[kept, SITES], base.loc[kept, SITES])

    def test_splits_follow_local_months_and_dst_and_can_be_overridden(self):
        base = read_solar_series(sorted(self.production.glob("*.parquet")), "53")
        periods = evaluation_periods(base.index)
        self.assertEqual(pd.Timestamp(periods["validation"]["start"]), pd.Timestamp("2024-04-30T22:00Z"))
        self.assertEqual(pd.Timestamp(periods["test"]["start"]), pd.Timestamp("2024-10-31T23:00Z"))
        custom = evaluation_periods(base.index, split_starts=["2024-04", "2024-08", "2024-10"])
        self.assertEqual(pd.Timestamp(custom["validation"]["start"]), pd.Timestamp("2024-03-31T22:00Z"))
        with self.assertRaises(ValueError):
            evaluation_periods(base.index, split_starts=["2024-08", "2024-04", "2024-10"])

    def test_scoring_uses_only_true_targets_reports_coverage_and_mwh(self):
        index = pd.date_range("2024-01-01", periods=3, freq="30min", tz="UTC")
        truth = pd.DataFrame({"true_value_wh": [0, 1e6, 2e6]}, index=index)
        predictions = pd.Series([0, 3e6], index=index[:2])
        result = score_reconstruction(truth, predictions)
        self.assertEqual(result["n_predicted"], 2)
        self.assertEqual(result["coverage"], 2 / 3)
        self.assertEqual(result["mae_mwh"], 1)
        self.assertAlmostEqual(result["rmse_mwh"], np.sqrt(2))
        self.assertEqual(result["bias_mwh"], 1)
        empty = score_reconstruction(truth, pd.Series(np.nan, index=index))
        self.assertEqual(empty["coverage"], 0)
        self.assertTrue(np.isnan(empty["mae_mwh"]))
        with self.assertRaises(ValueError):
            score_reconstruction(truth.assign(true_value_wh=np.nan), predictions)

    def test_raw_output_overlap_rejected_before_writing(self):
        for output in (self.raw, self.raw / "new", self.root):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "sans chevauchement"):
                prepare_evaluation(self.raw, output)

    def test_duration_weights_and_missing_predictions_are_explicit(self):
        index = pd.date_range("2024-01-01", periods=3, freq="30min", tz="UTC")
        truth = pd.DataFrame({"true_value_wh": [0, 1e6, 2e6], "duration_weight": [1., 3., 1.]}, index=index)
        predictions = pd.Series([0, 3e6], index=index[:2])
        result = score_reconstruction(truth, predictions, weight_column="duration_weight")
        self.assertEqual(result["coverage"], 2 / 3)
        self.assertEqual(result["weighted_coverage"], .8)
        self.assertEqual(result["mae_mwh"], 1.5)
        self.assertAlmostEqual(result["rmse_mwh"], np.sqrt(3))
        with self.assertRaises(ValueError):
            score_reconstruction(truth.assign(duration_weight=-1), predictions, weight_column="duration_weight")

    def test_modified_artifact_is_detected_instead_of_silently_reused(self):
        evaluation = self.prepare()
        path = evaluation / "truth.parquet"
        path.write_bytes(path.read_bytes() + b"modified")
        with self.assertRaisesRegex(ValueError, "modifié"):
            load_evaluation_split(evaluation, "test")

    def test_unknown_region_and_duplicate_source_fail_clearly(self):
        files = sorted(self.production.glob("*.parquet"))
        with self.assertRaisesRegex(ValueError, "Aucune production"):
            read_solar_series(files, "99")
        source = pd.read_parquet(files[0])
        pd.concat([source, source.iloc[:1]]).to_parquet(files[0], index=False)
        with self.assertRaisesRegex(ValueError, "répétées"):
            read_solar_series(files, "53")


if __name__ == "__main__":
    unittest.main()
