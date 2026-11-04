import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.imputation_baselines import compare_references, reconstruct_reference, run_references
from enedis.prediction.imputation_evaluation import ENERGY, SITES, STEP, prepare_evaluation


class ImputationBaselineTests(unittest.TestCase):
    def series(self, count=12 * 48, start="2024-01-01"):
        return pd.Series(np.arange(count, dtype=float),
                         index=pd.date_range(start, periods=count, freq="30min", tz="UTC", name="horodate"))

    def gap(self, series, start_position, length=1):
        start = series.index[start_position]
        return pd.DataFrame({"gap_id": ["g1"], "start": [start],
                             "end_exclusive": [start + length * STEP], "n_slots": [length]})

    def hide(self, series, gaps):
        result = series.copy()
        for _, gap in gaps.iterrows():
            result.loc[(result.index >= gap["start"]) & (result.index < gap["end_exclusive"])] = np.nan
        return result

    def test_linear_uses_only_two_borders_and_keeps_zero(self):
        source = pd.Series([0., 999., 888., 777., 4.], index=self.series(5).index)
        gaps = self.gap(source, 1, 3)
        masked = self.hide(source, gaps)
        before = masked.copy(deep=True)
        result = reconstruct_reference(masked, gaps, "linear")
        np.testing.assert_allclose(result["prediction_wh"], [1, 2, 3])
        self.assertEqual(result["n_support"].tolist(), [2, 2, 2])
        self.assertTrue(result["information"].eq("two_sided").all())
        self.assertTrue(result["information_cutoff"].eq(source.index[-1] + STEP).all())
        pd.testing.assert_series_equal(masked, before)

    def test_linear_does_not_extrapolate_open_gap(self):
        source = self.series(5)
        gaps = self.gap(source, 1, 3)
        masked = self.hide(source, gaps).iloc[:-1]
        result = reconstruct_reference(masked, gaps, "linear")
        self.assertTrue(result["prediction_wh"].isna().all())
        self.assertTrue(result["n_support"].eq(1).all())

    def test_previous_day_predicts_whole_block_without_recursion_or_future_values(self):
        source = self.series()
        gaps = self.gap(source, 48, 60)
        masked = self.hide(source, gaps)
        result = reconstruct_reference(masked, gaps, "previous_day", day_basis="utc")
        np.testing.assert_allclose(result.iloc[:48]["prediction_wh"], np.arange(48))
        self.assertTrue(result.iloc[48:]["prediction_wh"].isna().all())
        changed = masked.copy()
        changed.loc[changed.index >= gaps.iloc[0]["end_exclusive"]] = 1_000_000
        pd.testing.assert_frame_equal(result, reconstruct_reference(changed, gaps, "previous_day", day_basis="utc"))
        self.assertTrue(result["information_cutoff"].eq(gaps.iloc[0]["start"]).all())

    def test_seasonal_median_known_values_minimum_and_no_future_dependence(self):
        source = self.series()
        position = 9 * 48 + 20
        for day, value in enumerate([0., 10., np.nan, 30., 100., 200., np.nan], start=1):
            source.iloc[position - day * 48] = value
        gaps = self.gap(source, position)
        masked = self.hide(source, gaps)
        result = reconstruct_reference(masked, gaps, "seasonal_median", day_basis="utc")
        self.assertEqual(result.iloc[0]["prediction_wh"], 30)
        self.assertEqual(result.iloc[0]["n_support"], 5)
        strict = reconstruct_reference(masked, gaps, "seasonal_median", day_basis="utc", min_observations=6)
        self.assertTrue(strict["prediction_wh"].isna().all())
        changed = masked.copy()
        changed.loc[changed.index >= gaps.iloc[0]["end_exclusive"]] = 1e9
        pd.testing.assert_frame_equal(result, reconstruct_reference(changed, gaps, "seasonal_median", day_basis="utc"))

    def test_seasonal_median_does_not_fill_missing_daily_references(self):
        source = self.series()
        position = 9 * 48
        gaps = self.gap(source, position)
        masked = self.hide(source, gaps)
        for day in range(1, 8):
            masked.iloc[position - day * 48] = np.nan
        result = reconstruct_reference(masked, gaps, "seasonal_median", day_basis="utc")
        self.assertTrue(result["prediction_wh"].isna().all())
        self.assertEqual(result.iloc[0]["n_support"], 0)

    def test_local_day_differs_from_utc_at_spring_dst_and_ambiguous_hours_stay_missing(self):
        source = self.series(4 * 48, start="2024-03-30")
        position = int(source.index.get_loc(pd.Timestamp("2024-03-31T10:00Z")))
        gaps = self.gap(source, position)
        masked = self.hide(source, gaps)
        local = reconstruct_reference(masked, gaps, "previous_day", day_basis="local")
        utc = reconstruct_reference(masked, gaps, "previous_day", day_basis="utc")
        self.assertEqual(local.iloc[0]["prediction_wh"], 22)
        self.assertEqual(utc.iloc[0]["prediction_wh"], 20)
        autumn = self.series(4 * 48, start="2024-10-26")
        position = int(autumn.index.get_loc(pd.Timestamp("2024-10-28T01:00Z")))
        gaps = self.gap(autumn, position)
        result = reconstruct_reference(self.hide(autumn, gaps), gaps, "previous_day")
        self.assertTrue(result["prediction_wh"].isna().all())

    def test_common_scores_report_different_coverage_and_day_night(self):
        index = pd.to_datetime(["2024-06-21T00:00Z", "2024-06-21T12:00Z", "2024-06-21T23:30Z"])
        truth = pd.DataFrame({"true_value_wh": [0., 1e6, 0.], "duration_weight": 1., "n_slots": 1}, index=index)
        predictions = {
            "linear": pd.DataFrame({"prediction_wh": [0., 2e6, 0.]}, index=index),
            "previous_day": pd.DataFrame({"prediction_wh": [np.nan, 1e6, 0.]}, index=index),
        }
        scores = compare_references(truth, predictions, latitude=48., longitude=-3.)
        all_previous = scores.loc[scores["method"].eq("previous_day") & scores["scope"].eq("all_targets")
                                  & scores["stratum"].eq("overall")].iloc[0]
        self.assertEqual(all_previous["coverage"], 2 / 3)
        common = scores.loc[scores["scope"].eq("common_targets") & scores["stratum"].eq("overall")]
        self.assertEqual(common["n_total"].tolist(), [2, 2])
        self.assertEqual(common["mae_mwh"].tolist(), [.5, 0])
        day = scores.loc[scores["scope"].eq("all_targets") & scores["stratum"].eq("light")
                         & scores["stratum_value"].eq("day")]
        self.assertEqual(day["n_total"].tolist(), [1, 1])

    def test_common_scores_remain_undefined_when_one_method_cannot_predict_any_target(self):
        index = self.series(2).index
        truth = pd.DataFrame({"true_value_wh": 0., "duration_weight": 1., "n_slots": 1}, index=index)
        predictions = {"linear": pd.DataFrame({"prediction_wh": np.nan}, index=index)}
        scores = compare_references(truth, predictions)
        common = scores.loc[scores["scope"].eq("common_targets")]
        self.assertTrue(common["n_total"].eq(0).all())
        self.assertTrue(common["mae_mwh"].isna().all())

    def test_unmasked_targets_invalid_grid_and_invalid_options_rejected(self):
        source = self.series()
        gaps = self.gap(source, 48)
        with self.assertRaisesRegex(ValueError, "masquées"):
            reconstruct_reference(source, gaps, "linear")
        masked = self.hide(source, gaps)
        with self.assertRaises(ValueError):
            reconstruct_reference(masked.drop(masked.index[1]), gaps, "previous_day")
        for kwargs in [dict(method="unknown"), dict(method="seasonal_median", days=0),
                       dict(method="seasonal_median", min_observations=8), dict(method="linear", day_basis="x")]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                reconstruct_reference(masked, gaps, **kwargs)
        with self.assertRaises(ValueError):
            reconstruct_reference(masked, pd.concat([gaps, gaps]), "linear")

    def test_runner_exports_validation_only_reuses_cache_and_preserves_base_and_masks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw/production_regionale"
            raw.mkdir(parents=True)
            series = self.series(366 * 48)
            frame = pd.DataFrame({"horodate": series.index, ENERGY: series.to_numpy(), SITES: 100,
                                  "code_region": "53", "filiere_de_production": "F5 : Solaire",
                                  "plage_de_puissance_injection": "P0 : Total toutes puissances"})
            frame.loc[100:101, ENERGY] = np.nan
            frame.to_parquet(raw / "part.parquet", index=False)
            evaluation = prepare_evaluation(root / "raw", root / "imputed", gaps_per_split=2)
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in root.rglob("*") if p.is_file()}
            directory = run_references(evaluation)
            metadata = json.loads((directory / "manifest.json").read_text())
            self.assertEqual(metadata["split"], "validation")
            self.assertEqual(metadata["n_gaps"], 2)
            self.assertEqual((directory / metadata["evaluation_relative_path"]).resolve(), evaluation)
            for method in ("linear", "previous_day", "seasonal_median"):
                prediction = pd.read_parquet(directory / f"predictions_{method}.parquet")
                self.assertTrue(prediction["gap_id"].str.startswith("validation_").all())
                self.assertNotIn("true_value_wh", prediction)
            self.assertTrue((directory / "scores_global.csv").exists())
            cache = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.rglob("*") if p.is_file()}
            self.assertEqual(run_references(evaluation), directory)
            self.assertEqual(cache, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                     for p in directory.rglob("*") if p.is_file()})
            for path, content in before.items():
                self.assertEqual(content, (path.read_bytes(), path.stat().st_mtime_ns))


if __name__ == "__main__":
    unittest.main()
