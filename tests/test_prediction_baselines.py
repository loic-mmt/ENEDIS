from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.baselines import linear_baseline, persistance_baseline
from enedis.prediction.utils import verify_last_date


class HistoryValidationTests(unittest.TestCase):
    def test_older_history_is_valid_and_not_modified(self):
        frame = pd.DataFrame({"year": [2020, 2021]})
        original = frame.copy(deep=True)
        self.assertIsNone(verify_last_date(frame, "year", 2025))
        pd.testing.assert_frame_equal(frame, original)
        verify_last_date(pd.DataFrame({"year": ["2020", "2021"]}), "year", "2025")

    def test_future_date_rejected_even_if_not_last_row(self):
        with self.assertRaisesRegex(ValueError, "Données futures"):
            verify_last_date(pd.DataFrame({"year": [2026, 2020]}), "year", 2025)

    def test_offsets_compared_as_instants(self):
        frame = pd.DataFrame({"date": ["2025-01-01T00:00:00+01:00"]})
        verify_last_date(frame, "date", "2024-12-31T23:00:00Z")
        with self.assertRaisesRegex(ValueError, "Données futures"):
            verify_last_date(frame, "date", "2024-12-31T22:59:00Z")

    def test_invalid_histories_and_cutoffs(self):
        cases = [([], 2025), ([None], 2025), (["invalid"], "2025-01-01"),
                 ([""], "2025-01-01"), ([2025], None), ([2025], True),
                 ([2025], "2025-01-01"), ([2025.5], 2026),
                 (["2025-01-01"], None), (["2025-01-01"], "invalid")]
        for dates, cutoff in cases:
            with self.subTest(dates=dates, cutoff=cutoff):
                with self.assertRaises(ValueError):
                    verify_last_date(pd.DataFrame({"date": dates}), "date", cutoff)
        with self.assertRaisesRegex(ValueError, "absente"):
            verify_last_date(pd.DataFrame({"year": [2025]}), "missing", 2025)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({"year": [2022, 2023, 2024], "target": [100., 110., 120.]},
                                  index=[7, 8, 9])

    def predict(self, frame=None, horizon=3, cutoff=2024):
        return persistance_baseline(self.frame if frame is None else frame,
                                    "target", "year", cutoff, horizon)

    def test_last_value_repeated_without_mutation(self):
        original = self.frame.copy(deep=True)
        result = self.predict()
        self.assertIsInstance(result, np.ndarray)
        np.testing.assert_array_equal(result, [120., 120., 120.])
        pd.testing.assert_frame_equal(self.frame, original)

    def test_last_missing_value_skipped(self):
        self.frame.loc[9, "target"] = np.nan
        np.testing.assert_array_equal(self.predict(), [110., 110., 110.])

    def test_missing_target_produces_nan_not_zero(self):
        self.frame["target"] = np.nan
        self.assertTrue(np.isnan(self.predict()).all())

    def test_real_zero_preserved(self):
        self.frame.loc[9, "target"] = 0
        np.testing.assert_array_equal(self.predict(), [0., 0., 0.])

    def test_future_values_are_not_silently_filtered(self):
        with self.assertRaisesRegex(ValueError, "Données futures"):
            self.predict(cutoff=2023)

    def test_invalid_arguments(self):
        for horizon in [0, -1, 1.5, True]:
            with self.subTest(horizon=horizon), self.assertRaises(ValueError):
                self.predict(horizon=horizon)
        with self.assertRaises(ValueError):
            persistance_baseline(self.frame, "absent", "year", 2024, 1)
        with self.assertRaises(ValueError):
            self.predict(self.frame.assign(target=["a", "b", "c"]))


class LinearTests(unittest.TestCase):
    def predict(self, years, values, cutoff=2024, horizon=3, info_length=3):
        frame = pd.DataFrame({"year": years, "target": values}, index=range(10, 10 + len(years)))
        original = frame.copy(deep=True)
        result = linear_baseline(frame, "target", "year", cutoff, horizon, info_length)
        pd.testing.assert_frame_equal(frame, original)
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, (horizon,))
        return result

    def test_linear_trend_not_compound_growth(self):
        np.testing.assert_allclose(self.predict([2022, 2023, 2024], [100., 110., 120.]),
                                   [130., 140., 150.])

    def test_uses_actual_years_and_forecasts_after_cutoff(self):
        np.testing.assert_allclose(self.predict([2020, 2022], [100., 120.]),
                                   [150., 160., 170.])

    def test_window_uses_last_valid_observations(self):
        np.testing.assert_allclose(self.predict([2020, 2021, 2022, 2023, 2024],
                                               [999., 90., 100., np.nan, 120.], info_length=3),
                                   [130., 140., 150.])

    def test_single_observation_falls_back_to_persistence(self):
        np.testing.assert_allclose(self.predict([2023, 2024], [12., np.nan]), [12.] * 3)

    def test_all_missing_returns_nan(self):
        self.assertTrue(np.isnan(self.predict([2023, 2024], [np.nan, np.nan])).all())

    def test_zero_history_and_negative_extrapolation(self):
        np.testing.assert_allclose(self.predict([2022, 2023, 2024], [0., 0., 0.]), [0.] * 3)
        np.testing.assert_allclose(self.predict([2022, 2023, 2024], [20., 10., 0.]), [0.] * 3)

    def test_calendar_dates(self):
        np.testing.assert_allclose(self.predict(["2022-12-31", "2024-12-31"], [100., 120.],
                                               cutoff="2024-12-31"), [130., 140., 150.])

    def test_year_strings(self):
        np.testing.assert_allclose(self.predict(["2022", "2023", "2024"], [100., 110., 120.],
                                               cutoff="2024"), [130., 140., 150.])

    def test_invalid_window(self):
        for window in [0, -1, True, 1.5, 1]:
            with self.subTest(window=window), self.assertRaises(ValueError):
                self.predict([2023, 2024], [10., 20.], info_length=window)

    def test_invalid_history_and_future_values(self):
        for years, values in [([2023, 2024], [10., np.inf]),
                              ([2024, 2024], [10., 20.]),
                              ([2024, 2023], [10., 20.]),
                              ([2024, 2025], [10., 20.])]:
            with self.subTest(years=years, values=values), self.assertRaises(ValueError):
                self.predict(years, values)


if __name__ == "__main__":
    unittest.main()
