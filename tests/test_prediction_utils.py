from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.utils import (
    check_aligned_series, check_collection, check_column, check_dataframe,
    check_datetime_index, check_finite, check_integer, check_numeric,
    check_real, check_timestamp,
)


class ValidationTests(unittest.TestCase):
    def test_integer_bounds_numpy_and_strict_contract(self):
        check_integer(np.int64(2), "window", minimum=2, maximum=3)
        for value in (True, np.bool_(True), 2., 1, 4):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "window"):
                check_integer(value, "window", minimum=2, maximum=3)
        with self.assertRaises(ValueError):
            check_integer(np.int64(2), "year", strict=True)

    def test_real_bounds_and_positive_values(self):
        check_real(-90., "latitude", minimum=-90, maximum=90)
        check_real(1e-9, "epsilon", positive=True)
        for value in (True, np.nan, np.inf, "2", 91.):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_real(value, "latitude", minimum=-90, maximum=90)
        with self.assertRaises(ValueError):
            check_real(0., "epsilon", positive=True)

    def test_collections_generators_choices_and_empty_lags(self):
        result = check_collection((x for x in [1, 3]), "lags", integers=True, minimum=1)
        self.assertEqual(result, [1, 3])
        self.assertEqual(check_collection([], "lags", allow_empty=True), [])
        for values in ("A", None, [], ["A", "A"], ["Z"], [["A"]]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                check_collection(values, "groups", choices={"A": (), "B": ()})

    def test_table_structure_without_mutation(self):
        frame = pd.DataFrame({"x": [1], "target": [2.]})
        before = frame.copy(deep=True)
        check_dataframe(frame, required=["target"], nonempty=True, string_columns=True)
        check_column(frame, "target")
        pd.testing.assert_frame_equal(frame, before)
        with self.assertRaises(TypeError):
            check_dataframe([])
        with self.assertRaises(ValueError):
            check_dataframe(frame, required=["absent"])
        with self.assertRaises(ValueError):
            check_column(pd.concat([frame, frame], axis=1), "target")
        with self.assertRaises(ValueError):
            check_dataframe(frame.iloc[:0], nonempty=True)

    def test_nullable_numeric_series_missing_and_finite_rules(self):
        series = pd.Series([0., None, 2.], dtype="Float64", name="energy")
        before = series.copy(deep=True)
        check_numeric(series, minimum=0, integer=True)
        pd.testing.assert_series_equal(series, before)
        with self.assertRaises(ValueError):
            check_numeric(series, allow_missing=False)
        for values in ([np.inf], [-1.], [True], [1j], ["1"], [1.5]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                check_numeric(pd.Series(values), "energy", minimum=0, integer=True)
        check_numeric(pd.Series([None]), "energy")
        with self.assertRaises(ValueError):
            check_numeric(pd.Series([None]), "energy", allow_empty=False)
        check_finite([1., np.nan], "predictions", allow_missing=True)
        with self.assertRaises(ValueError):
            check_finite([1., np.inf], "predictions", allow_missing=True)

    def test_date_grid_uses_utc_across_dst(self):
        index = pd.date_range("2025-10-26", periods=10, freq="30min", tz="Europe/Paris")
        check_datetime_index(index, ordered=True, nonempty=True, step="30min", regular=True)
        for bad in (index.tz_localize(None), index[::-1], index.delete(3), index + pd.Timedelta(minutes=1)):
            with self.subTest(index=bad), self.assertRaises(ValueError):
                check_datetime_index(bad, ordered=True, step="30min", regular=True)
        with self.assertRaises(ValueError):
            check_datetime_index(index.append(index[:1]))

    def test_timestamp_aware_and_aligned(self):
        self.assertEqual(check_timestamp("2025-01-01T01:00+01:00"), pd.Timestamp("2025-01-01T00:00Z"))
        for value in (None, "bad", "2025-01-01", "2025-01-01T01:01Z"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_timestamp(value, step="30min")

    def test_aligned_series_never_reorders_rows(self):
        values = pd.Series([1., 2.], index=[3, 2])
        check_aligned_series(values, pd.Index([3, 2]))
        with self.assertRaises(ValueError):
            check_aligned_series(values, pd.Index([2, 3]))


if __name__ == "__main__":
    unittest.main()
