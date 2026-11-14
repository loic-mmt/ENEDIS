from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.exceptions import NotFittedError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.imputation_evaluation import ENERGY, STEP, score_reconstruction
from enedis.prediction.imputation_models import reconstruct_with_model
from enedis.prediction.models import predict
from enedis.prediction.sarima import SARIMARegressor, SARIMAXRegressor


class SARIMATests(unittest.TestCase):
    def setUp(self):
        self.index = pd.date_range('2025-10-25', periods=90, freq='30min', tz='Europe/Paris', name='horodate')
        self.X = pd.DataFrame(index=self.index[:70])
        self.y = pd.Series(1e6 + np.sin(np.arange(70) * 2*np.pi/4)*2e5, index=self.X.index, name=ENERGY)

    def model(self, **kwargs):
        return SARIMARegressor(order=(1, 0, 0), seasonal_order=(0, 1, 0, 4), maxiter=30, **kwargs)

    def test_fit_predict_original_units_and_time_holes_preserved(self):
        removed = [10, 11, 12]
        X, y = self.X.drop(self.X.index[removed]), self.y.drop(self.y.index[removed])
        before_X, before_y = X.copy(), y.copy()
        model = self.model().fit(X, y)
        result = predict(model, pd.DataFrame(index=self.index[70:74]))
        self.assertTrue(np.isfinite(result).all())
        self.assertGreater(result.min(), 1e5)
        self.assertEqual(model.n_context_, 67)
        self.assertEqual(model.n_time_steps_, 70)
        self.assertEqual(model.model_.endog.shape[0], 70)
        self.assertTrue(np.isnan(model.model_.endog[removed]).all())
        self.assertEqual(model.context_index_.tolist(), X.index.tz_convert('UTC').tolist())
        self.assertIsInstance(model.converged_, bool)
        pd.testing.assert_frame_equal(before_X, X)
        pd.testing.assert_series_equal(before_y, y)
        pd.testing.assert_index_equal(result.index, self.index[70:74])

    def test_sparse_query_dates_map_to_elapsed_steps(self):
        model = self.model().fit(self.X, self.y)
        contiguous = model.predict(pd.DataFrame(index=self.index[70:76]))
        sparse = model.predict(pd.DataFrame(index=self.index[[70, 73, 75]]))
        np.testing.assert_allclose(sparse, contiguous[[0, 3, 5]])
        self.assertEqual(model.predict(pd.DataFrame(index=self.index[:0])).shape, (0,))
        with self.assertRaises(ValueError):
            model.predict(self.X.iloc[[-1]])

    def test_default_seasonality_and_sklearn_clone(self):
        model = SARIMARegressor()
        self.assertEqual(model.order, (1, 0, 1))
        self.assertEqual(model.seasonal_order, (1, 1, 1, 48))
        self.assertEqual(clone(model).get_params(), model.get_params())
        with self.assertRaises(NotFittedError):
            model.predict(self.X)

    def test_scaling_is_fitted_on_past_and_predictions_are_rescaled(self):
        first = self.model().fit(self.X, self.y)
        second = self.model().fit(self.X, self.y * 1000.)
        query = pd.DataFrame(index=self.index[70:73])
        np.testing.assert_allclose(second.predict(query) / 1000., first.predict(query), rtol=1e-5)

    def test_invalid_training_data_and_orders(self):
        cases = [dict(order=(1, 0)), dict(order=(True, 0, 0)), dict(seasonal_order=(1, 1, 1, 1)),
                 dict(maxiter=0), dict(trend='bad')]
        for options in cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                SARIMARegressor(**options).fit(self.X, self.y)
        for y in (self.y.iloc[::-1], self.y* np.nan, self.y.astype('string'), self.y.replace(self.y.iloc[0], np.inf)):
            with self.assertRaises(ValueError):
                self.model().fit(self.X, y)
        with self.assertRaises(ValueError):
            SARIMARegressor().fit(self.X, self.y)  # Moins de deux journées.
        with self.assertRaises(ValueError):
            self.model().fit(self.X.set_axis(self.X.index.tz_localize(None)), self.y)

    def test_reconstruction_same_mask_forward_clipping_and_no_feature_builder(self):
        inputs = pd.DataFrame({ENERGY: np.r_[self.y.to_numpy(), np.full(20, 2e6)], 'is_observed': True}, index=self.index)
        inputs.loc[self.index[70:73], ENERGY] = np.nan
        inputs.loc[self.index[70:73], 'is_observed'] = False
        gaps = pd.DataFrame({'gap_id':['validation_0'], 'split':['validation'], 'start':[self.index[70]],
                             'end_exclusive':[self.index[73]], 'n_slots':[3],
                             'reconstruction_as_of':[self.index[-1] + STEP]})
        before = inputs.copy(deep=True)
        with patch('enedis.prediction.imputation_models.build_production_features') as builder:
            predictions, diagnostics = reconstruct_with_model(inputs, gaps, self.model(),
                latitude=48., longitude=-3., context_size=64, groups=())
        builder.assert_not_called()
        self.assertTrue(predictions.prediction_wh.ge(0).all())
        self.assertEqual(diagnostics.n_train.tolist(), [64])
        self.assertTrue((diagnostics.context_end < diagnostics.start).all())
        changed = inputs.copy()
        changed.loc[changed.index >= self.index[73], ENERGY] = 1e15
        other, _ = reconstruct_with_model(changed, gaps, self.model(), latitude=48., longitude=-3.,
                                          context_size=64, groups=())
        pd.testing.assert_frame_equal(predictions, other)
        pd.testing.assert_frame_equal(before, inputs)
        truth = pd.DataFrame({'true_value_wh': 1e6, 'duration_weight': 1.}, index=predictions.index)
        self.assertEqual(score_reconstruction(truth, predictions.prediction_wh)['coverage'], 1.)


class SARIMAXTests(unittest.TestCase):
    def setUp(self):
        self.index = pd.date_range('2025-01-01', periods=180, freq='30min', tz='UTC', name='horodate')
        rng = np.random.default_rng(42)
        self.X = pd.DataFrame({
            'signal': rng.normal(size=180),
            'lag': rng.normal(size=180),
            'empty_lag': np.nan,
            'season': pd.Categorical(np.where(np.arange(180) % 2, 'winter', 'spring')),
        }, index=self.index)
        self.X.loc[self.index[10:13], 'lag'] = np.nan
        self.y = pd.Series(2e6 + self.X.signal * 3e5 + rng.normal(0, 1e3, 180),
                           index=self.index, name=ENERGY)

    def model(self):
        return SARIMAXRegressor(order=(0, 0, 0), seasonal_order=(0, 0, 0, 0), trend='c', maxiter=50)

    def test_covariates_affect_predictions_and_preprocessing_uses_only_training(self):
        train = self.X.iloc[:150].copy()
        before = train.copy(deep=True)
        model = self.model().fit(train, self.y.iloc[:150])
        self.assertTrue(model.uses_features)
        self.assertGreater(model.n_exog_, 0)
        self.assertEqual(clone(model).get_params(), model.get_params())
        imputer = model.preprocessor_.named_transformers_['numeric'].steps[0][1]
        np.testing.assert_allclose(imputer.statistics_[:2], train[['signal', 'lag']].median())
        query = self.X.iloc[150:155].copy()
        baseline = predict(model, query)
        query['signal'] += 2
        changed = predict(model, query)
        np.testing.assert_allclose(changed - baseline, 6e5, rtol=.02)
        pd.testing.assert_frame_equal(train, before)

    def test_missing_covariates_and_time_holes_preserve_target_missingness(self):
        removed = self.index[20:23]
        train = self.X.iloc[:150].drop(removed)
        y = self.y.loc[train.index].copy()
        y.iloc[30] = np.nan
        model = self.model().fit(train, y)
        self.assertEqual(model.n_time_steps_, 150)
        self.assertTrue(np.isnan(model.model_.endog[20:23]).all())
        self.assertTrue(np.isfinite(model.model_.exog).all())
        query = self.X.iloc[150:155].copy()
        query['lag'] = np.nan
        result = predict(model, query)
        self.assertTrue(np.isfinite(result).all())
        pd.testing.assert_series_equal(predict(model, query.iloc[:, ::-1]), result)
        with self.assertRaisesRegex(ValueError, 'chaque demi-heure'):
            model.predict(query.iloc[[0, 2]])
        with self.assertRaises(ValueError):
            model.predict(query.drop(columns='lag'))
        with self.assertRaises(ValueError):
            self.model().fit(pd.DataFrame(index=train.index), y)

    def test_forward_abc_includes_bridge_covariates_without_future_labels(self):
        inputs = pd.DataFrame({ENERGY: self.y, 'is_observed': True})
        inputs.loc[self.index[148:153], ENERGY] = np.nan
        inputs.loc[self.index[148:153], 'is_observed'] = False
        gaps = pd.DataFrame({'gap_id': ['validation_0'], 'split': ['validation'],
                             'start': [self.index[150]], 'end_exclusive': [self.index[153]], 'n_slots': [3],
                             'reconstruction_as_of': [self.index[-1] + STEP]})
        before = inputs.copy(deep=True)
        model = self.model()
        predictions, diagnostics = reconstruct_with_model(inputs, gaps, model,
            latitude=48.17, longitude=-2.95, context_size=128, groups=('A', 'B', 'C'))
        self.assertEqual(diagnostics.groups.tolist(), ['A+B+C'])
        self.assertEqual(len(model.feature_names_in_), 15)
        self.assertTrue(predictions.prediction_wh.ge(0).all())
        changed = inputs.copy()
        changed.loc[self.index[153]:, ENERGY] = 1e15
        other, _ = reconstruct_with_model(changed, gaps, self.model(),
            latitude=48.17, longitude=-2.95, context_size=128, groups=('A', 'B', 'C'))
        pd.testing.assert_frame_equal(predictions, other)
        pd.testing.assert_frame_equal(inputs, before)


if __name__ == '__main__':
    unittest.main()
