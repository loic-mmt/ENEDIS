from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.features import (
    PRODUCTION_FEATURE_GROUPS,
    build_production_features,
    create_astro_features,
    create_calendar_features,
    create_decomposition_features,
    create_lag_features,
    create_rolling_features,
    create_sites_features,
)
from enedis.prediction import features


class ProductionFeatureTests(unittest.TestCase):
    def frame(self, count=100, start="2024-01-01", values=None):
        return pd.DataFrame({
            "horodate": pd.date_range(start, periods=count, freq="30min", tz="UTC"),
            "total_energie_injectee_wh": np.arange(count, dtype=float) + 1 if values is None else values,
            "nb_points_injection": np.arange(count) + 100,
            "code_region": "53",
        })

    def seasonal_frame(self):
        count = 32 * 48 + 1
        x = np.arange(count)
        return self.frame(count, values=20 + .02 * x + 5 * np.sin(2 * np.pi * x / 48))

    def test_calendar_local_time_regular_grid_and_no_mutation(self):
        frame = self.frame(3, start="2024-06-30 22:00").drop(index=1).iloc[::-1]
        before = frame.copy(deep=True)
        result = create_calendar_features(frame)
        pd.testing.assert_frame_equal(frame, before)
        self.assertEqual(str(result.index.tz), "UTC")
        self.assertEqual(result.index.name, "horodate")
        self.assertEqual(len(result), 3)
        self.assertTrue(pd.isna(result.iloc[1]["total_energie_injectee_wh"]))
        self.assertEqual(result["month"].tolist(), [7, 7, 7])
        self.assertEqual(result["week_of_year"].tolist(), [27, 27, 27])
        self.assertEqual(result["day_of_week"].tolist(), [0, 0, 0])
        self.assertEqual(result["season"].tolist(), ["summer"] * 3)
        self.assertIsInstance(result["season"].dtype, pd.CategoricalDtype)
        self.assertAlmostEqual(result.iloc[0]["hour_sin"], 0)
        self.assertAlmostEqual(result.iloc[1]["hour_sin"], np.sin(2 * np.pi * .5 / 24))

    def test_calendar_seasons_leap_day_and_utc_configuration(self):
        for month, season in [(1, "winter"), (4, "spring"), (7, "summer"), (10, "autumn")]:
            with self.subTest(month=month):
                result = create_calendar_features(self.frame(1, start=f"2024-{month:02d}-01"), timezone="UTC")
                self.assertEqual(result.iloc[0]["season"], season)
        row = create_calendar_features(self.frame(1, start="2024-02-29 12:00"), timezone="UTC").iloc[0]
        self.assertAlmostEqual(row["doy_sin"], np.sin(2 * np.pi * 60.5 / 365.2425))
        self.assertAlmostEqual(row["hour_cos"], -1)

    def test_astro_summer_winter_night_and_day(self):
        summer = create_astro_features(self.frame(48, start="2024-06-21"), 48., -3.)
        winter = create_astro_features(self.frame(48, start="2024-12-21"), 48., -3.)
        self.assertLess(summer.iloc[0]["solar_elevation"], 0)
        self.assertGreater(summer.loc["2024-06-21 12:00:00+00:00", "solar_elevation"], 50)
        self.assertTrue(summer["solar_azimuth"].between(0, 360).all())
        self.assertTrue(summer["daylight_duration"].between(15, 17).all())
        self.assertTrue(winter["daylight_duration"].between(8, 10).all())
        self.assertGreater(summer.iloc[0]["daylight_duration"], winter.iloc[0]["daylight_duration"])

    def test_lags_use_exact_instants_not_existing_row_offsets(self):
        frame = self.frame(100).drop(index=48)
        result = create_lag_features(frame)
        self.assertTrue(pd.isna(result.iloc[96]["lag_1d"]))
        self.assertEqual(result.iloc[97]["lag_1d"], 50)
        self.assertEqual(result.iloc[96]["lag_2d"], 1)
        self.assertTrue(pd.isna(result.iloc[96]["lag_7d"]))

    def test_lag_utc_and_same_local_hour_differ_at_dst(self):
        frame = self.frame(4 * 48, start="2024-03-30")
        utc = create_lag_features(frame)
        local = create_lag_features(frame, basis="local")
        target = pd.Timestamp("2024-03-31 10:00", tz="UTC")
        self.assertEqual(utc.loc[target, "lag_1d"], 21)
        self.assertEqual(local.loc[target, "lag_1d"], 23)
        self.assertTrue(pd.isna(local.loc["2024-04-01 00:00:00+00:00", "lag_1d"]))
        autumn = create_lag_features(self.frame(4 * 48, start="2024-10-26"), basis="local")
        self.assertTrue(pd.isna(autumn.loc["2024-10-28 01:00:00+00:00", "lag_1d"]))

    def test_rolling_windows_exclude_current_observation_and_require_complete_data(self):
        frame = self.frame(30 * 48 + 2)
        result = create_rolling_features(frame)
        self.assertAlmostEqual(result.iloc[336]["rolling_mean_7d"], np.mean(np.arange(336) + 1))
        self.assertAlmostEqual(result.iloc[336]["rolling_std_7d"], np.std(np.arange(336) + 1, ddof=1))
        self.assertAlmostEqual(result.iloc[1440]["rolling_q95_30d"], np.quantile(np.arange(1440) + 1, .95))
        self.assertEqual(result.iloc[2]["ramp_rate"], 1)
        frame.loc[336, "total_energie_injectee_wh"] = 1e9
        changed = create_rolling_features(frame)
        pd.testing.assert_series_equal(result.iloc[336][list(PRODUCTION_FEATURE_GROUPS["D"])],
                                       changed.iloc[336][list(PRODUCTION_FEATURE_GROUPS["D"])])
        frame.loc[0, "total_energie_injectee_wh"] = np.nan
        self.assertTrue(pd.isna(create_rolling_features(frame).iloc[336]["rolling_mean_7d"]))

    def test_sites_shift_growth_and_yoy_quantile_ratio(self):
        count = 400 * 48 + 1
        production = np.where(np.arange(count) < 365 * 48, 10., 20.)
        frame = self.frame(count, values=production)
        result = create_sites_features(frame)
        i = len(frame) - 1
        row = result.iloc[i]
        current = frame.iloc[i - 1]["nb_points_injection"]
        reference = frame.iloc[i - 1 - 30 * 48]["nb_points_injection"]
        self.assertEqual(row["n_sites_solar"], current)
        self.assertAlmostEqual(row["n_sites_growth_30d"], (current - reference) / reference)
        reference = frame.iloc[i - 1 - 365 * 48]["nb_points_injection"]
        self.assertAlmostEqual(row["n_sites_growth_yoy"], (current - reference) / reference)
        self.assertAlmostEqual(row["growth_yoy_q95"], 2, places=8)
        frame.loc[i, "nb_points_injection"] = 1_000_000
        self.assertEqual(create_sites_features(frame).iloc[i]["n_sites_solar"], current)

    def test_zero_site_reference_missing_counts_and_nullable_types(self):
        frame = self.frame(32 * 48)
        frame["nb_points_injection"] = pd.Series(0, index=frame.index, dtype="Int64")
        frame.loc[len(frame) - 2, "nb_points_injection"] = pd.NA
        result = create_sites_features(frame)
        self.assertEqual(result.iloc[-2]["n_sites_solar"], 0)
        self.assertTrue(result["n_sites_growth_30d"].isna().all())
        self.assertTrue(pd.isna(result.iloc[-1]["n_sites_solar"]))

    def test_as_of_masks_observations_at_and_after_issuance(self):
        frame = self.frame(10 * 48 + 1)
        cutoff = frame.iloc[8 * 48]["horodate"]
        groups = ("C", "D", "E")
        result = build_production_features(frame, groups, as_of=cutoff)
        changed = frame.copy()
        changed.loc[changed["horodate"] >= cutoff, "total_energie_injectee_wh"] = 1e9
        changed.loc[changed["horodate"] >= cutoff, "nb_points_injection"] = 1_000_000
        pd.testing.assert_frame_equal(result, build_production_features(changed, groups, as_of=cutoff))
        self.assertTrue(pd.isna(result.loc[cutoff + pd.Timedelta(days=1), "lag_1d"]))
        self.assertEqual(result.loc[cutoff, "n_sites_solar"], frame.iloc[8 * 48 - 1]["nb_points_injection"])
        self.assertTrue(pd.isna(result.loc[cutoff + pd.Timedelta(minutes=30), "n_sites_solar"]))

    def test_stl_components_are_causal_and_have_known_trend_units(self):
        frame = self.seasonal_frame()
        result = create_decomposition_features(frame)
        i = 30 * 48
        self.assertTrue(result.iloc[:i][list(PRODUCTION_FEATURE_GROUPS["F"])].isna().all().all())
        self.assertAlmostEqual(result.iloc[i]["trend"], 20 + .02 * i, places=4)
        self.assertAlmostEqual(result.iloc[i]["trend_slope_30d"], .96, places=4)
        self.assertAlmostEqual(result.iloc[i]["seasonal"], 0, places=4)
        self.assertAlmostEqual(result.iloc[i]["residual_lag"], 0, places=4)
        changed = frame.copy()
        changed.loc[i:, "total_energie_injectee_wh"] += 1_000_000
        row = create_decomposition_features(changed).iloc[i]
        np.testing.assert_allclose(row[list(PRODUCTION_FEATURE_GROUPS["F"])].to_numpy(dtype=float),
                                   result.iloc[i][list(PRODUCTION_FEATURE_GROUPS["F"])].to_numpy(dtype=float))
        truncated = create_decomposition_features(frame.iloc[:i + 1])
        pd.testing.assert_frame_equal(truncated[list(PRODUCTION_FEATURE_GROUPS["F"])],
                                      result.iloc[:i + 1][list(PRODUCTION_FEATURE_GROUPS["F"])])

    def test_stl_missing_history_not_interpolated(self):
        frame = self.seasonal_frame()
        frame.loc[10 * 48, "total_energie_injectee_wh"] = np.nan
        result = create_decomposition_features(frame)
        self.assertTrue(result[list(PRODUCTION_FEATURE_GROUPS["F"])].isna().all().all())

    def test_builder_all_groups_no_targets_no_mutation_and_fixed_origin_invariance(self):
        frame = self.seasonal_frame()
        frame["future_information"] = 999
        before = frame.copy(deep=True)
        cutoff = frame.iloc[30 * 48]["horodate"]
        kwargs = dict(latitude=48., longitude=-3., as_of=cutoff)
        result = build_production_features(frame, **kwargs)
        pd.testing.assert_frame_equal(frame, before)
        self.assertEqual(result.columns.tolist(), [name for group in PRODUCTION_FEATURE_GROUPS.values() for name in group])
        self.assertEqual(result.shape[1], 27)
        self.assertNotIn("total_energie_injectee_wh", result)
        self.assertNotIn("nb_points_injection", result)
        self.assertNotIn("future_information", result)
        changed = frame.copy()
        changed.loc[changed["horodate"] >= cutoff, "total_energie_injectee_wh"] += 1e6
        changed.loc[changed["horodate"] >= cutoff, "nb_points_injection"] += 1_000_000
        pd.testing.assert_frame_equal(result, build_production_features(changed, **kwargs))
        self.assertTrue(pd.notna(result.iloc[-1]["trend"]))
        self.assertTrue(pd.isna(result.iloc[-1]["residual_lag"]))

    def test_selected_groups_need_only_their_input_columns(self):
        frame = self.frame(2)[["horodate"]]
        calendar = build_production_features(frame, groups=("A",))
        self.assertEqual(calendar.columns.tolist(), list(PRODUCTION_FEATURE_GROUPS["A"]))
        astro = build_production_features(frame, groups=("B",), latitude=48., longitude=-3.)
        self.assertEqual(astro.columns.tolist(), list(PRODUCTION_FEATURE_GROUPS["B"]))
        custom = self.frame(60).rename(columns={"total_energie_injectee_wh": "production_mwh"})
        result = create_lag_features(custom, value_column="production_mwh")
        self.assertEqual(result.iloc[48]["lag_1d"], 1)

    def test_builder_prepares_once_and_matches_selected_standalone_groups(self):
        frame = self.frame(32 * 48 + 1)
        cutoff = frame.iloc[31 * 48]['horodate']
        groups = ('E', 'A', 'D', 'C')
        columns = [name for group in groups for name in PRODUCTION_FEATURE_GROUPS[group]]
        with patch.object(features, '_production_frame', wraps=features._production_frame) as prepare:
            actual = build_production_features(frame, groups, as_of=cutoff)
        prepare.assert_called_once()
        expected = pd.concat([
            create_sites_features(frame, as_of=cutoff)[list(PRODUCTION_FEATURE_GROUPS['E'])],
            create_calendar_features(frame)[list(PRODUCTION_FEATURE_GROUPS['A'])],
            create_rolling_features(frame, as_of=cutoff)[list(PRODUCTION_FEATURE_GROUPS['D'])],
            create_lag_features(frame, as_of=cutoff)[list(PRODUCTION_FEATURE_GROUPS['C'])],
        ], axis=1)
        self.assertEqual(actual.columns.tolist(), columns)
        pd.testing.assert_frame_equal(actual, expected)

    def test_explicit_offsets_distinguish_repeated_local_hours(self):
        frame = pd.DataFrame({"horodate": ["2024-10-27T02:00:00+02:00", "2024-10-27T02:00:00+01:00"]})
        cutoff = pd.Timestamp("2024-10-27 01:00", tz="UTC").tz_convert("Europe/Paris")
        result = build_production_features(frame, groups=("A",), as_of=cutoff)
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result.iloc[0]["hour_sin"], result.iloc[2]["hour_sin"])
        self.assertNotEqual(result.index[0], result.index[2])

    def test_all_missing_observations_remain_missing(self):
        frame = self.frame(100)
        frame["total_energie_injectee_wh"] = None
        frame["nb_points_injection"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
        result = build_production_features(frame, groups=("C", "D", "E"))
        self.assertTrue(result.isna().all().all())

    def test_reject_invalid_series_dates_values_and_parameters(self):
        frame = self.frame(4)
        bad_frames = [frame.iloc[:0], pd.concat([frame, frame.iloc[:1]]),
                      frame.assign(horodate=frame["horodate"].dt.tz_localize(None)),
                      frame.assign(horodate=frame["horodate"] + pd.Timedelta(minutes=1)),
                      frame.assign(code_region=["53", "11", "53", "11"])]
        for bad in bad_frames:
            with self.subTest(kind="frame"), self.assertRaises(ValueError):
                create_calendar_features(bad)
        for values in [[1, 2, -1, 3], [1, 2, np.inf, 3], ["1", "2", "3", "4"]]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                create_lag_features(frame.assign(total_energie_injectee_wh=values))
        for groups in [(), ("Z",), ("A", "A"), "A"]:
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                build_production_features(frame, groups=groups)
        with self.assertRaises(ValueError):
            create_astro_features(frame, 91, 0)
        with self.assertRaises(ValueError):
            create_sites_features(frame.assign(nb_points_injection=1.5))
        with self.assertRaises(ValueError):
            create_lag_features(frame, basis="unknown")
        with self.assertRaises(ValueError):
            create_lag_features(frame, as_of="2024-01-01")
        with self.assertRaises(ValueError):
            create_decomposition_features(frame, refit_every="31min")


if __name__ == "__main__":
    unittest.main()
