from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.contracts import PredictionRequest
from enedis.prediction.pipeline import run_baseline


class BaselinePipelineTests(unittest.TestCase):
    def setUp(self):
        self.history = pd.DataFrame({
            "code_commune": ["01001", "2A004"] * 4,
            "annee": [2022, 2022, 2023, 2023, 2024, 2024, 2025, 2025],
            "consommation_mwh": [100., 200., 110., 220., 120., 240., 9999., 9999.],
            "puissance_pv_mw": [1., 3., 2., 4., 3., 5., 999., 999.],
        }, index=range(10, 18))
        self.request = PredictionRequest("consommation_mwh", 2024, 2)

    def test_persistence_per_commune_no_future_leakage_or_mutation(self):
        original = self.history.copy(deep=True)
        result = run_baseline(self.history, self.request, "persistance")
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(result.columns.tolist(), ["code_commune", "target", "origin_year",
                                                  "prediction_year", "prediction", "model"])
        self.assertEqual(result["code_commune"].tolist(), ["01001", "01001", "2A004", "2A004"])
        self.assertEqual(result["prediction_year"].tolist(), [2025, 2026] * 2)
        self.assertEqual(result["prediction"].tolist(), [120., 120., 240., 240.])
        self.assertEqual(result["origin_year"].tolist(), [2024] * 4)
        self.assertEqual(result["target"].tolist(), ["consommation_mwh"] * 4)
        self.assertEqual(result["model"].tolist(), ["persistance"] * 4)
        pd.testing.assert_frame_equal(self.history, original)

    def test_linear_forecasts_use_correct_commune(self):
        result = run_baseline(self.history, self.request, "linear", info_length=3)
        np.testing.assert_allclose(result["prediction"], [130., 140., 260., 280.])
        self.assertEqual(result["model"].tolist(), ["linear"] * 4)

    def test_second_target(self):
        request = PredictionRequest("puissance_pv_mw", 2024, 1)
        result = run_baseline(self.history, request, "persistance")
        self.assertEqual(result["prediction"].tolist(), [3., 5.])
        self.assertEqual(result["target"].tolist(), ["puissance_pv_mw"] * 2)

    def test_window_parameter_reaches_linear_baseline(self):
        history = self.history.copy()
        history.loc[10, "consommation_mwh"] = 1000.
        result = run_baseline(history, self.request, "linear", info_length=2)
        np.testing.assert_allclose(result["prediction"], [130., 140., 260., 280.])

    def test_missing_target_remains_nan(self):
        history = self.history.copy()
        history.loc[history["code_commune"] == "01001", "consommation_mwh"] = np.nan
        for method in ["persistance", "linear"]:
            with self.subTest(method=method):
                result = run_baseline(history, self.request, method)
                self.assertTrue(result.loc[result["code_commune"] == "01001", "prediction"].isna().all())

    def test_commune_with_only_future_history_is_not_dropped(self):
        history = self.history.loc[(self.history["code_commune"] != "01001")
                                   | (self.history["annee"] > 2024)]
        result = run_baseline(history, self.request, "linear")
        self.assertEqual(len(result), 4)
        unavailable = result.loc[result["code_commune"] == "01001", "prediction"]
        self.assertEqual(len(unavailable), 2)
        self.assertTrue(unavailable.isna().all())

    def test_old_history_forecasts_after_request_origin(self):
        request = PredictionRequest("consommation_mwh", 2026, 1)
        history = self.history.loc[self.history["annee"] <= 2023]
        result = run_baseline(history, request, "linear")
        self.assertEqual(result["prediction_year"].tolist(), [2027, 2027])
        np.testing.assert_allclose(result["prediction"], [150., 300.])

    def test_invalid_method_and_request(self):
        with self.assertRaisesRegex(ValueError, "baseline"):
            run_baseline(self.history, self.request, "unknown")
        with self.assertRaises(TypeError):
            run_baseline(self.history, {}, "persistance")

    def test_history_contract_enforced(self):
        cases = [self.history.drop(columns="annee"), self.history.iloc[:0],
                 pd.concat([self.history, self.history.iloc[:1]]), self.history.iloc[::-1]]
        for history in cases:
            with self.subTest(rows=len(history)), self.assertRaises(ValueError):
                run_baseline(history, self.request, "persistance")

    def test_invalid_window_even_when_no_past_observations(self):
        history = self.history.loc[self.history["annee"] > 2024]
        for window in [1, 0, True, 2.5]:
            with self.subTest(window=window), self.assertRaises(ValueError):
                run_baseline(history, self.request, "linear", info_length=window)


if __name__ == "__main__":
    unittest.main()
