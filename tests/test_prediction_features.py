from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.features import build_features


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.history = pd.DataFrame({
            "code_commune": ["01001"] * 4,
            "annee": [2020, 2021, 2022, 2024],
            "consommation_mwh": [10., 20., 30., 50.],
            "puissance_pv_mw": [1., 2., 3., 5.],
            "future_information": [999.] * 4,
        }, index=[7, 7, 11, 19])

    def test_known_annual_features_and_input_unchanged(self):
        before = self.history.copy(deep=True)
        result = build_features(self.history, "consommation_mwh")
        pd.testing.assert_frame_equal(self.history, before)
        self.assertEqual(result.index.tolist(), self.history.index.tolist())
        self.assertEqual(result[["code_commune", "annee"]].to_dict("list"),
                         self.history[["code_commune", "annee"]].to_dict("list"))
        row = result.loc[result["annee"] == 2022].iloc[0]
        self.assertEqual(row["consommation_mwh_current"], 30.)
        self.assertEqual(row["consommation_mwh_lag_1"], 20.)
        self.assertEqual(row["consommation_mwh_lag_2"], 10.)
        self.assertTrue(pd.isna(row["consommation_mwh_lag_3"]))
        self.assertEqual(row["consommation_mwh_change_1y"], 10.)
        self.assertEqual(row["consommation_mwh_mean_3y"], 20.)
        self.assertEqual(row["consommation_mwh_count_3y"], 3)
        self.assertNotIn("future_information", result)
        self.assertNotIn("puissance_pv_mw", result)
        self.assertNotIn("consommation_mwh", result)

    def test_missing_year_is_not_previous_row(self):
        result = build_features(self.history, "consommation_mwh")
        row = result.loc[result["annee"] == 2024].iloc[0]
        self.assertTrue(pd.isna(row["consommation_mwh_lag_1"]))
        self.assertEqual(row["consommation_mwh_lag_2"], 30.)
        self.assertEqual(row["consommation_mwh_lag_3"], 20.)
        self.assertTrue(pd.isna(row["consommation_mwh_change_1y"]))
        self.assertTrue(pd.isna(row["consommation_mwh_mean_3y"]))
        self.assertEqual(row["consommation_mwh_count_3y"], 2)

    def test_future_values_cannot_change_past_features(self):
        original = build_features(self.history, "consommation_mwh")
        changed = self.history.copy()
        changed.loc[changed["annee"] > 2021, "consommation_mwh"] = 1_000_000.
        result = build_features(changed, "consommation_mwh")
        pd.testing.assert_frame_equal(original.loc[original["annee"] <= 2021],
                                      result.loc[result["annee"] <= 2021])
        truncated = build_features(self.history.loc[self.history["annee"] <= 2021],
                                   "consommation_mwh")
        pd.testing.assert_frame_equal(truncated, original.loc[original["annee"] <= 2021])

    def test_communes_are_independent_even_when_interleaved(self):
        other = self.history.assign(code_commune="2A004", consommation_mwh=1000.)
        combined = pd.concat([self.history, other]).sort_values("annee", kind="stable")
        result = build_features(combined, "consommation_mwh")
        selected = result.loc[result["code_commune"] == "01001"]
        pd.testing.assert_frame_equal(selected, build_features(self.history, "consommation_mwh"))
        row = result.loc[(result["code_commune"] == "2A004") & (result["annee"] == 2022)].iloc[0]
        self.assertEqual(row["consommation_mwh_mean_3y"], 1000.)

    def test_missing_current_value_is_not_imputed(self):
        history = self.history.copy()
        history.loc[history["annee"] == 2022, "consommation_mwh"] = np.nan
        row = build_features(history, "consommation_mwh").iloc[2]
        self.assertTrue(pd.isna(row["consommation_mwh_current"]))
        self.assertTrue(pd.isna(row["consommation_mwh_mean_3y"]))
        self.assertEqual(row["consommation_mwh_lag_1"], 20.)
        self.assertEqual(row["consommation_mwh_count_3y"], 2)

    def test_all_missing_target_and_nullable_types(self):
        history = self.history.copy().astype({"annee": "Int64"})
        history["consommation_mwh"] = pd.Series(pd.NA, index=history.index, dtype="Float64")
        result = build_features(history, "consommation_mwh")
        self.assertTrue(result.filter(regex="current|lag|change|mean").isna().all().all())
        self.assertEqual(result["consommation_mwh_count_3y"].tolist(), [0] * 4)
        history["consommation_mwh"] = None
        self.assertTrue(build_features(history, "consommation_mwh")["consommation_mwh_current"].isna().all())

    def test_zero_is_a_real_observation(self):
        history = self.history.assign(consommation_mwh=0.)
        row = build_features(history, "consommation_mwh").iloc[2]
        self.assertEqual(row["consommation_mwh_mean_3y"], 0.)
        self.assertEqual(row["consommation_mwh_change_1y"], 0.)
        self.assertEqual(row["consommation_mwh_count_3y"], 3)

    def test_second_target_and_configurable_features(self):
        result = build_features(self.history, "puissance_pv_mw", lags=(2,), rolling_window=2)
        row = result.iloc[2]
        self.assertNotIn("puissance_pv_mw_lag_1", result)
        self.assertEqual(row["puissance_pv_mw_lag_2"], 1.)
        self.assertEqual(row["puissance_pv_mw_change_1y"], 1.)
        self.assertEqual(row["puissance_pv_mw_mean_2y"], 2.5)
        self.assertEqual(row["puissance_pv_mw_count_2y"], 2)

    def test_invalid_parameters(self):
        cases = [dict(target="unknown"), dict(lags="123"), dict(lags=1),
                 dict(lags=(1, 1)), dict(lags=(True,)), dict(lags=(0,)),
                 dict(lags=(-1,)), dict(lags=(1.5,)), dict(rolling_window=0),
                 dict(rolling_window=True), dict(rolling_window=2.5)]
        for overrides in cases:
            kwargs = dict(target="consommation_mwh")
            kwargs.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                build_features(self.history, **kwargs)

    def test_history_contract_enforced(self):
        cases = [self.history.iloc[:0], self.history.drop(columns="annee"),
                 pd.concat([self.history, self.history.iloc[:1]]), self.history.iloc[::-1]]
        for history in cases:
            with self.subTest(rows=len(history)), self.assertRaises(ValueError):
                build_features(history, "consommation_mwh")


if __name__ == "__main__":
    unittest.main()
