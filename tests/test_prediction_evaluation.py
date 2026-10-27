from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.contracts import PredictionRequest
from enedis.prediction.evaluation import MAE, RMSE, backtest_baselines, evaluate_baseline


class BaselineEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.history = pd.DataFrame({
            "code_commune": ["01001", "2A004"] * 3,
            "annee": [2022, 2022, 2023, 2023, 2024, 2024],
            "consommation_mwh": [100., 200., 110., 220., 130., 260.],
            "puissance_pv_mw": [10., 30., 20., 40., 21., 42.],
        }, index=[5, 9, 11, 14, 30, 42])
        self.request = PredictionRequest("consommation_mwh", 2023, 2)

    def test_metrics_match_real_future_values_by_commune_and_year(self):
        original = self.history.copy(deep=True)
        self.assertEqual(MAE(self.history, self.request, "persistance"), 30.)
        self.assertAlmostEqual(RMSE(self.history, self.request, "persistance"), np.sqrt(1000.))
        pd.testing.assert_frame_equal(self.history, original)

    def test_both_scores_use_single_baseline_call_and_report_coverage(self):
        from enedis.prediction.pipeline import run_baseline
        with patch("enedis.prediction.evaluation.run_baseline", wraps=run_baseline) as run:
            scores = evaluate_baseline(self.history, self.request, "persistance")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(scores["n_predictions"], 4)
        self.assertEqual(scores["n_evaluated"], 2)
        self.assertEqual(scores["mae"], 30.)

    def test_second_target(self):
        request = PredictionRequest("puissance_pv_mw", 2023, 1)
        self.assertEqual(MAE(self.history, request, "persistance"), 1.5)
        self.assertAlmostEqual(RMSE(self.history, request, "persistance"), np.sqrt(2.5))

    def test_linear_prediction_scores(self):
        scores = evaluate_baseline(self.history, self.request, "linear", info_length=2)
        self.assertAlmostEqual(scores["mae"], 15.)  # Forecasts 120 and 240, truth 130 and 260.
        self.assertAlmostEqual(scores["rmse"], np.sqrt(250.))

    def test_missing_actual_is_not_zero(self):
        history = self.history.copy()
        history.loc[30, "consommation_mwh"] = np.nan
        scores = evaluate_baseline(history, self.request, "persistance")
        self.assertEqual(scores["n_evaluated"], 1)
        self.assertEqual(scores["mae"], 40.)

    def test_missing_prediction_is_not_zero(self):
        history = self.history.copy()
        history.loc[(history["code_commune"] == "01001") & (history["annee"] <= 2023),
                    "consommation_mwh"] = np.nan
        scores = evaluate_baseline(history, self.request, "persistance")
        self.assertEqual(scores["n_evaluated"], 1)
        self.assertEqual(scores["mae"], 40.)

    def test_no_evaluable_pairs_is_explicit_error(self):
        cases = [self.history.loc[self.history["annee"] <= 2023],
                 self.history.assign(consommation_mwh=np.nan)]
        for history in cases:
            with self.subTest(rows=len(history)), self.assertRaisesRegex(ValueError, "Aucune paire"):
                evaluate_baseline(history, self.request, "persistance")

    def test_zero_actual_is_evaluated(self):
        history = self.history.copy()
        history.loc[30, "consommation_mwh"] = 0.
        scores = evaluate_baseline(history, self.request, "persistance")
        self.assertEqual(scores["n_evaluated"], 2)
        self.assertEqual(scores["mae"], 75.)

    def test_duplicate_history_rejected(self):
        history = pd.concat([self.history, self.history.iloc[-1:]])
        with self.assertRaisesRegex(ValueError, "Doublons"):
            evaluate_baseline(history, self.request, "persistance")


class BaselineBacktestTests(unittest.TestCase):
    def setUp(self):
        self.history = pd.DataFrame({
            "code_commune": ["01001", "2A004"] * 5,
            "annee": [2020, 2020, 2021, 2021, 2022, 2022, 2023, 2023, 2024, 2024],
            "consommation_mwh": [100., 200., 110., 220., 125., 250., 130., 260., 150., 300.],
            "puissance_pv_mw": [1., 2., 2., 4., 3., 6., 4., 8., 5., 10.],
        }, index=range(10, 20))

    def test_details_and_scores_by_horizon_without_mutation_or_recalculation(self):
        from enedis.prediction.pipeline import run_baseline
        before = self.history.copy(deep=True)
        with patch("enedis.prediction.evaluation.run_baseline", wraps=run_baseline) as run:
            details, scores = backtest_baselines(
                self.history, "consommation_mwh", [2021, 2022], 2, info_length=2)
        self.assertEqual(run.call_count, 4)  # One call per origin and baseline.
        self.assertEqual(len(details), 16)
        self.assertEqual(len(scores), 4)  # One row per baseline and horizon.
        pd.testing.assert_frame_equal(self.history, before)
        self.assertTrue(details["evaluated"].all())
        self.assertTrue((details["horizon"] == details["prediction_year"] - details["origin_year"]).all())
        np.testing.assert_allclose(details["error"], details["prediction"] - details["actual"])
        persistence = scores.loc[(scores["model"] == "persistance") & (scores["horizon"] == 1)].iloc[0]
        self.assertEqual(persistence["mae"], 15.)
        self.assertAlmostEqual(persistence["rmse"], np.sqrt(312.5))
        self.assertEqual(persistence["bias"], -15.)
        self.assertEqual(persistence["n_evaluated"], 4)
        self.assertEqual(persistence["coverage"], 1.)
        linear = scores.loc[(scores["model"] == "linear") & (scores["horizon"] == 1)].iloc[0]
        self.assertAlmostEqual(linear["mae"], 11.25)
        self.assertAlmostEqual(linear["rmse"], 12.5)
        self.assertAlmostEqual(linear["bias"], 3.75)

    def test_future_truth_changes_errors_not_forecasts_for_fixed_origin(self):
        original, _ = backtest_baselines(self.history, "consommation_mwh", [2021], 2)
        history = self.history.copy()
        history.loc[history["annee"] > 2021, "consommation_mwh"] += 1000
        changed, _ = backtest_baselines(history, "consommation_mwh", [2021], 2)
        np.testing.assert_allclose(original["prediction"], changed["prediction"])
        np.testing.assert_allclose(changed["error"], original["error"] - 1000)

    def test_unavailable_horizons_keep_nan_scores_and_zero_coverage(self):
        details, scores = backtest_baselines(self.history, "consommation_mwh", [2023], 2)
        second_year = scores.loc[scores["horizon"] == 2]
        self.assertTrue(second_year[["mae", "rmse", "bias"]].isna().all().all())
        self.assertEqual(second_year["n_predictions"].tolist(), [2, 2])
        self.assertEqual(second_year["n_evaluated"].tolist(), [0, 0])
        self.assertEqual(second_year["coverage"].tolist(), [0., 0.])
        self.assertTrue(details.loc[details["horizon"] == 2, "actual"].isna().all())

    def test_models_are_scored_on_common_observations(self):
        from enedis.prediction.pipeline import run_baseline

        def missing_linear(*args, **kwargs):
            predictions = run_baseline(*args, **kwargs)
            if args[2] == "linear":
                predictions.loc[predictions["code_commune"] == "01001", "prediction"] = np.nan
            return predictions

        with patch("enedis.prediction.evaluation.run_baseline", side_effect=missing_linear):
            details, scores = backtest_baselines(self.history, "consommation_mwh", [2021], 1)
        self.assertEqual(scores["n_evaluated"].tolist(), [1, 1])
        self.assertEqual(scores["n_available"].tolist(), [2, 1])
        self.assertTrue((~details.loc[details["code_commune"] == "01001", "evaluated"]).all())
        persistence = scores.loc[scores["model"] == "persistance"].iloc[0]
        self.assertEqual(persistence["mae"], 30.)

    def test_second_target_and_zero_actual(self):
        history = self.history.copy()
        history.loc[(history["annee"] == 2022) & (history["code_commune"] == "01001"), "puissance_pv_mw"] = 0.
        details, scores = backtest_baselines(history, "puissance_pv_mw", [2021], 1,
                                            baseline_types=["persistance"])
        self.assertEqual(scores["n_evaluated"].tolist(), [2])
        self.assertEqual(scores["mae"].tolist(), [2.])
        self.assertEqual(details["target"].unique().tolist(), ["puissance_pv_mw"])

    def test_single_unevaluable_origin_does_not_abort_backtest(self):
        _, scores = backtest_baselines(self.history, "consommation_mwh", [2019, 2021], 1)
        self.assertEqual(scores["n_predictions"].tolist(), [4, 4])
        self.assertEqual(scores["n_evaluated"].tolist(), [2, 2])

    def test_invalid_settings(self):
        cases = [dict(origin_years=[]), dict(origin_years=[2021, 2021]),
                 dict(origin_years=[True]), dict(origin_years="2021"),
                 dict(baseline_types=[]), dict(baseline_types=["unknown"]),
                 dict(baseline_types=["linear", "linear"]),
                 dict(baseline_types="linear"), dict(horizon=0), dict(target="unknown"),
                 dict(info_length=1)]
        for overrides in cases:
            settings = dict(target="consommation_mwh", origin_years=[2021], horizon=1)
            settings.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                backtest_baselines(self.history, **settings)


if __name__ == "__main__":
    unittest.main()
