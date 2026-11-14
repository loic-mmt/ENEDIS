from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.features import PRODUCTION_FEATURE_GROUPS, build_production_features
from enedis.prediction.imputation_evaluation import (
    ENERGY, SITES, STEP, load_evaluation_split, prepare_evaluation, score_reconstruction,
)
from enedis.prediction.imputation_models import prepare_model_features, reconstruct_with_model


class RecordingRegressor:
    def __init__(self):
        self.fits = []
        self.queries = []

    def fit(self, X, y):
        self.fits.append((X.copy(deep=True), y.copy(deep=True)))
        self.mean = float(y.mean())
        self.feature_names_in_ = np.array(X.columns, dtype=object)
        return self

    def predict(self, X):
        self.queries.append(X.copy(deep=True))
        return np.full(len(X), self.mean)


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        # Inclut le changement d'heure : horodates locales répétées, instants distincts.
        self.index = pd.date_range("2025-10-25", periods=144, freq="30min", tz="Europe/Paris", name="horodate")
        self.inputs = pd.DataFrame({ENERGY: 1e6 + np.arange(144) * 1000., "is_observed": True}, index=self.index)
        self.gaps = self.make_gaps([(70, 3), (110, 2)])
        for position, length in [(70, 3), (110, 2), (50, 1)]:
            self.inputs.iloc[position:position + length, 0] = np.nan
            self.inputs.iloc[position:position + length, 1] = False
        self.inputs.iloc[0, 0] = 0.  # Zéro publié, observation valide.

    def make_gaps(self, specs):
        return pd.DataFrame([{
            "gap_id": f"validation_{number}", "split": "validation", "start": self.index[position],
            "end_exclusive": self.index[position] + length * STEP, "n_slots": length,
            "reconstruction_as_of": self.index[-1] + STEP,
        } for number, (position, length) in enumerate(specs)])

    def run_model(self, inputs=None, gaps=None, model=None, **options):
        return reconstruct_with_model(
            self.inputs if inputs is None else inputs,
            self.gaps if gaps is None else gaps,
            RecordingRegressor() if model is None else model,
            latitude=48., longitude=-3., **options,
        )

    def test_whole_blocks_only_abc_features_and_no_source_mutation(self):
        before_inputs, before_gaps = self.inputs.copy(deep=True), self.gaps.copy(deep=True)
        model = RecordingRegressor()
        with patch("enedis.prediction.imputation_models.build_production_features", wraps=build_production_features) as builder:
            predictions, diagnostics = self.run_model(gaps=self.gaps.iloc[::-1], model=model, context_size=10)
        builder.assert_called_once()
        supplied = builder.call_args.args[0]
        self.assertEqual(supplied.columns.tolist(), [ENERGY])  # Production masquée pour calculer C.
        expected_series = self.inputs[ENERGY].where(self.inputs.is_observed).tz_convert("UTC")
        pd.testing.assert_series_equal(supplied[ENERGY], expected_series)
        self.assertEqual(builder.call_args.kwargs["groups"], ("A", "B", "C"))
        expected_columns = list(PRODUCTION_FEATURE_GROUPS["A"] + PRODUCTION_FEATURE_GROUPS["B"]
                                + PRODUCTION_FEATURE_GROUPS["C"])
        for (X, y), (_, gap), query in zip(model.fits, self.gaps.iterrows(), model.queries):
            start = gap["start"].tz_convert("UTC")
            expected = self.inputs[ENERGY].dropna().loc[lambda s: s.index < start].iloc[-10:]
            pd.testing.assert_index_equal(y.index, expected.index.tz_convert("UTC"))
            np.testing.assert_array_equal(y, expected)
            self.assertEqual(X.columns.tolist(), expected_columns)
            self.assertEqual(query.columns.tolist(), expected_columns)
            self.assertTrue((X.index < start).all())
            self.assertEqual(len(query), gap["n_slots"])
            self.assertNotIn(ENERGY, X)
        self.assertEqual(len(model.fits), 2)
        self.assertEqual(diagnostics["n_context"].tolist(), [10, 10])
        self.assertTrue(diagnostics["status"].eq("ok").all())
        self.assertTrue(diagnostics["groups"].eq("A+B+C").all())
        self.assertTrue((diagnostics["context_end"] < diagnostics["start"]).all())
        self.assertTrue(diagnostics[["fit_seconds", "predict_seconds"]].ge(0).all().all())
        self.assertEqual(len(predictions), 5)
        self.assertTrue(predictions.index.is_unique)
        self.assertEqual(str(predictions.index.tz), "UTC")
        self.assertTrue(predictions["information"].eq("past_only").all())
        pd.testing.assert_frame_equal(self.inputs, before_inputs)
        pd.testing.assert_frame_equal(self.gaps, before_gaps)

    def test_future_observations_do_not_affect_earlier_block(self):
        original_model = RecordingRegressor()
        original, _ = self.run_model(model=original_model)
        changed = self.inputs.copy()
        mask = (changed.index >= self.gaps.iloc[0].end_exclusive) & changed[ENERGY].notna()
        changed.loc[mask, ENERGY] = 1e15
        changed["true_value_wh"] = 1e30  # Colonne étrangère : jamais transmise au modèle.
        other_model = RecordingRegressor()
        actual, _ = self.run_model(inputs=changed, model=other_model)
        first = original.gap_id.eq("validation_0")
        pd.testing.assert_frame_equal(original.loc[first], actual.loc[first])
        for original_arg, actual_arg in zip(original_model.fits[0], other_model.fits[0]):
            if isinstance(original_arg, pd.DataFrame):
                pd.testing.assert_frame_equal(original_arg, actual_arg)
            else:
                pd.testing.assert_series_equal(original_arg, actual_arg)

    def test_reused_features_preserve_predictions_and_contexts(self):
        expected_model, actual_model = RecordingRegressor(), RecordingRegressor()
        expected, _ = self.run_model(model=expected_model)
        features = prepare_model_features(self.inputs, self.gaps, latitude=48., longitude=-3.)
        before = features.copy(deep=True)
        with patch('enedis.prediction.imputation_models.build_production_features') as builder:
            actual, _ = self.run_model(model=actual_model, features=features, quiet=True)
        builder.assert_not_called()
        pd.testing.assert_frame_equal(actual, expected)
        pd.testing.assert_frame_equal(features, before)
        for expected_fit, actual_fit in zip(expected_model.fits, actual_model.fits):
            pd.testing.assert_frame_equal(expected_fit[0], actual_fit[0])
            pd.testing.assert_series_equal(expected_fit[1], actual_fit[1])

    def test_predictions_and_unobserved_labels_never_enter_later_context(self):
        model = RecordingRegressor()
        inputs = self.inputs.copy()
        inputs.iloc[5, 0] = 1e15
        inputs.iloc[5, 1] = False  # Une estimation déjà présente n'est pas une observation.
        self.run_model(inputs=inputs, model=model, context_size=None)
        for _, y in model.fits:
            self.assertNotIn(self.index[5], y.index)
            self.assertNotIn(self.index[50], y.index)
            self.assertEqual(y.iloc[0], 0.)
        first_gap = pd.date_range(self.gaps.iloc[0].start, periods=3, freq="30min")
        self.assertFalse(model.fits[1][1].index.isin(first_gap).any())
        expected_count = 110 - 3 - 1 - 1
        self.assertEqual(len(model.fits[1][1]), expected_count)

    def test_calibration_and_test_rows_are_excluded_before_features(self):
        extra_index = pd.date_range(self.index[-1] + STEP, periods=4, freq="30min", name="horodate")
        extra = pd.DataFrame({ENERGY: np.inf, "is_observed": True}, index=extra_index)
        extended = pd.concat([self.inputs, extra])
        with patch("enedis.prediction.imputation_models.build_production_features", wraps=build_production_features) as builder:
            actual, _ = self.run_model(inputs=extended)
        expected, _ = self.run_model()
        pd.testing.assert_frame_equal(actual, expected)
        self.assertEqual(builder.call_args.args[0].index[-1], self.index[-1].tz_convert("UTC"))

    def test_insufficient_context_keeps_nan_then_resumes(self):
        inputs = self.inputs.copy()
        inputs.loc[inputs.index < self.gaps.iloc[0].start, "is_observed"] = False
        inputs.iloc[0, 1] = True  # Une seule observation au premier trou.
        model = RecordingRegressor()
        predictions, diagnostics = self.run_model(inputs=inputs, model=model, min_observations=3)
        self.assertEqual(diagnostics.status.tolist(), ["insufficient_context", "ok"])
        self.assertEqual(diagnostics.iloc[0].n_context, 0)
        self.assertTrue(pd.isna(diagnostics.iloc[0].context_start))
        self.assertEqual(diagnostics.iloc[0].fit_seconds, 0.)
        self.assertTrue(predictions.loc[predictions.gap_id.eq("validation_0"), "prediction_wh"].isna().all())
        self.assertEqual(len(model.fits), 1)

    def test_default_kumo_is_created_once_and_refitted(self):
        model = RecordingRegressor()
        with patch("enedis.prediction.imputation_models.KumoTabularRegressor", return_value=model) as constructor:
            reconstruct_with_model(self.inputs, self.gaps, latitude=48., longitude=-3., context_size=8)
        constructor.assert_called_once_with(context_size=None)
        self.assertEqual([len(y) for _, y in model.fits], [8, 8])

    def test_progress_receives_independent_diagnostics_in_chronological_order(self):
        events = []

        def progress(info):
            events.append(info.copy())
            info["status"] = "changed by callback"

        _, diagnostics = self.run_model(gaps=self.gaps.iloc[::-1], on_gap_end=progress)
        self.assertEqual([info["gap_id"] for info in events], diagnostics.gap_id.tolist())
        self.assertTrue(diagnostics.status.eq("ok").all())

    def test_invalid_progress_callback_rejected(self):
        with self.assertRaisesRegex(TypeError, "on_gap_end"):
            self.run_model(on_gap_end=True)

    def test_sklearn_model_wh_units_and_scoring(self):
        predictions, diagnostics = self.run_model(model=DummyRegressor(strategy="mean"))
        expected = self.inputs[ENERGY].loc[self.inputs.index < self.gaps.iloc[0].start].mean()
        self.assertAlmostEqual(predictions.iloc[0].prediction_wh, expected)
        truth = pd.DataFrame({"true_value_wh": np.full(len(predictions), 2e6)}, index=predictions.index)
        scores = score_reconstruction(truth, predictions.prediction_wh)
        error = (predictions.prediction_wh.to_numpy() - 2e6) / 1e6
        self.assertAlmostEqual(scores["mae_mwh"], np.abs(error).mean())
        self.assertEqual(scores["coverage"], 1.)

    def test_partial_predictions_are_clipped_with_raw_values_preserved(self):
        model = RecordingRegressor()
        model.predict = lambda X: np.r_[-1., np.full(len(X) - 1, np.nan)]
        predictions, diagnostics = self.run_model(model=model)
        self.assertTrue(diagnostics.status.eq("partial_prediction").all())
        self.assertEqual(predictions.iloc[0].prediction_wh, 0.)
        self.assertEqual(predictions.iloc[0].prediction_raw_wh, -1.)
        np.testing.assert_array_equal(predictions.prediction_wh.isna(), predictions.prediction_raw_wh.isna())
        self.assertEqual(diagnostics.n_clipped.tolist(), [1, 1])
        self.assertEqual(diagnostics.n_predicted.tolist(), [1, 1])

    def test_utc_lags_use_only_observations_including_at_dst(self):
        model = RecordingRegressor()
        self.run_model(model=model)
        observed = self.inputs[ENERGY].where(self.inputs.is_observed).tz_convert("UTC")
        for (X, _), query in zip(model.fits, model.queries):
            for frame in (X, query):
                for days in (1, 2, 7, 365):
                    expected = observed.reindex(frame.index - pd.Timedelta(days=days)).to_numpy()
                    np.testing.assert_allclose(frame[f"lag_{days}d"], expected, equal_nan=True)

    def test_long_gap_lags_do_not_use_values_inside_the_block(self):
        inputs = self.inputs.copy()
        inputs.iloc[70:130, 0] = np.nan  # Trou de 30 h : J−1 finit par pointer dans le trou.
        inputs.iloc[70:130, 1] = False
        gaps = self.make_gaps([(70, 60)])
        model = RecordingRegressor()
        self.run_model(inputs=inputs, gaps=gaps, model=model)
        query = model.queries[0]
        self.assertTrue(query.lag_1d.iloc[:48].notna().any())
        self.assertTrue(query.lag_1d.iloc[48:].isna().all())

    def test_ab_remains_available_without_production_features(self):
        model = RecordingRegressor()
        with patch("enedis.prediction.imputation_models.build_production_features", wraps=build_production_features) as builder:
            _, diagnostics = self.run_model(model=model, groups=("A", "B"))
        self.assertEqual(builder.call_args.args[0].shape[1], 0)
        self.assertEqual(model.fits[0][0].shape[1], 11)
        self.assertTrue(diagnostics.groups.eq("A+B").all())

    def test_internal_kumo_context_limit_is_reported(self):
        class CappedRegressor(RecordingRegressor):
            def fit(self, X, y):
                self.context_index_ = X.index[-3:]
                return super().fit(X.iloc[-3:], y.iloc[-3:])
        _, diagnostics = self.run_model(model=CappedRegressor(), context_size=10)
        self.assertEqual(diagnostics.n_train.tolist(), [10, 10])
        self.assertEqual(diagnostics.n_context.tolist(), [3, 3])

    def test_only_validation_and_consistent_phase_cutoff_allowed(self):
        for split in ("calibration", "test"):
            with self.subTest(split=split), self.assertRaises(ValueError):
                self.run_model(gaps=self.gaps.assign(split=split))
        different_limits = self.gaps.copy()
        different_limits.loc[1, "reconstruction_as_of"] += STEP
        with self.assertRaises(ValueError):
            self.run_model(gaps=different_limits)
        with self.assertRaises(ValueError):
            self.run_model(gaps=self.gaps.assign(reconstruction_as_of=self.gaps.iloc[0].start + STEP))

    def test_invalid_mask_overlap_and_observed_flags(self):
        revealed = self.inputs.copy()
        revealed.iloc[70, 0] = 10.
        with self.assertRaisesRegex(ValueError, "masquées"):
            self.run_model(inputs=revealed)
        overlap = self.gaps.copy()
        overlap.loc[1, "start"] = self.gaps.iloc[0].start
        overlap.loc[1, "end_exclusive"] = self.gaps.iloc[0].start + 2 * STEP
        with self.assertRaisesRegex(ValueError, "chevauchent"):
            self.run_model(gaps=overlap)
        for flags in (pd.Series(1, index=self.index), pd.Series(pd.NA, index=self.index, dtype="boolean")):
            with self.assertRaises(ValueError):
                self.run_model(inputs=self.inputs.assign(is_observed=flags))

    def test_invalid_parameters_and_model(self):
        for options in ({"context_size": 1}, {"context_size": True}, {"min_observations": 1},
                        {"context_size": 2, "min_observations": 3}, {"groups": ("A", "D")},
                        {"groups": ("A", "A")}, {"groups": "ABC"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.run_model(**options)
        with self.assertRaises(TypeError):
            self.run_model(model=object())
        with self.assertRaises(ValueError):
            self.run_model(inputs=self.inputs.set_axis(self.index.tz_localize(None)))

    def test_model_failure_propagates(self):
        model = RecordingRegressor()
        def fail(X, y):
            raise RuntimeError("fit impossible")
        model.fit = fail
        with self.assertRaisesRegex(RuntimeError, "fit impossible"):
            self.run_model(model=model)

    def test_end_to_end_prepared_validation_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw" / "production_regionale"
            raw.mkdir(parents=True)
            index = pd.date_range("2024-01-01", "2024-07-01", freq="30min", inclusive="left", tz="UTC")
            source = pd.DataFrame({"horodate": index, ENERGY: 1e6, SITES: 100., "code_region": "53",
                                   "filiere_de_production": "F5 : Solaire",
                                   "plage_de_puissance_injection": "P0 : Total toutes puissances"})
            source.loc[100:101, ENERGY] = np.nan
            source.to_parquet(raw / "part.parquet", index=False)
            evaluation = prepare_evaluation(root / "raw", root / "imputed", gaps_per_split=1)
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            inputs, truth, gaps = load_evaluation_split(evaluation, "validation")
            predictions, diagnostics = self.run_model(inputs, gaps, model=DummyRegressor())
            pd.testing.assert_index_equal(predictions.index, truth.index)
            scores = score_reconstruction(truth, predictions.prediction_wh, weight_column="duration_weight")
            self.assertEqual(scores["mae_mwh"], 0.)
            self.assertEqual(scores["coverage"], 1.)
            self.assertEqual(diagnostics.status.tolist(), ["ok"])
            self.assertEqual(before, {path: path.read_bytes() for path in root.rglob("*") if path.is_file()})


if __name__ == "__main__":
    unittest.main()
