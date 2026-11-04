from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.exceptions import NotFittedError
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.models import KumoTabular_model, KumoTabularRegressor, predict


class Table:
    def __init__(self, data, stypes=None, device=None):
        self.data = data.copy()
        self.stypes = stypes

    @classmethod
    def from_pandas(cls, df, stypes, device):
        return cls(df, stypes, device)

    def select_columns(self, columns):
        return Table(self.data[columns])

    def cpu(self):
        return self

    def to_pandas(self):
        return self.data.copy()


class GenericPredictionTests(unittest.TestCase):
    def setUp(self):
        self.X = pd.DataFrame({"a": [1., 2., 3.], "b": [3., 1., 4.]}, index=[8, 2, 6])
        self.y = pd.Series([2., 4., 6.], index=self.X.index, name="target")

    def test_sklearn_and_pipeline_reorder_features_keep_index(self):
        for model in (LinearRegression(), make_pipeline(StandardScaler(), LinearRegression())):
            with self.subTest(model=model):
                model.fit(self.X, self.y)
                query = self.X[["b", "a"]]
                before = query.copy(deep=True)
                result = predict(model, query)
                np.testing.assert_allclose(result, self.y)
                pd.testing.assert_index_equal(result.index, query.index)
                pd.testing.assert_frame_equal(query, before)
                self.assertEqual(result.name, "prediction")

    def test_invalid_schema_rejected_before_prediction(self):
        model = LinearRegression().fit(self.X, self.y)
        for query in (self.X.drop(columns="a"), self.X.assign(target=self.y)):
            with self.assertRaisesRegex(ValueError, "features"):
                predict(model, query)

    def test_missing_prediction_is_preserved_and_column_vector_supported(self):
        result = predict(SimpleNamespace(predict=lambda X: np.array([[1.], [np.nan], [3.]])), self.X)
        self.assertTrue(np.isnan(result.iloc[1]))

    def test_invalid_output_rejected(self):
        for values in ([1.], np.ones((3, 2)), np.array([1., np.inf, 3.]),
                       ["1", "2", "3"], np.array(2.), np.array([1j, 2j, 3j])):
            with self.subTest(values=values), self.assertRaises(ValueError):
                predict(SimpleNamespace(predict=lambda X: values), self.X)
        with self.assertRaises(TypeError):
            predict(object(), self.X)

    def test_pandas_output_must_keep_index(self):
        expected = self.y.rename("prediction")
        pd.testing.assert_series_equal(predict(SimpleNamespace(predict=lambda X: self.y), self.X), expected)
        with self.assertRaisesRegex(ValueError, "index"):
            predict(SimpleNamespace(predict=lambda X: self.y.iloc[::-1]), self.X)


class KumoAdapterTests(unittest.TestCase):
    def setUp(self):
        self.index = pd.date_range("2025-01-01", periods=7, freq="30min", tz="UTC")
        self.df = pd.DataFrame({
            "x": np.arange(7, dtype=float),
            "season": pd.Categorical(["winter"] * 7),
            "target": [0., 1., np.nan, 3., 4., 5., 6.],
        }, index=self.index)
        self.backend = Mock()
        self.backend.predict.side_effect = lambda table: Table(pd.DataFrame({
            "q001": np.full(len(table.data), -999.),
            "q500": table.data["x"].to_numpy() * 2.,
            "q999": np.full(len(table.data), 999.),
        }))
        self.constructor = Mock(return_value=self.backend)
        self.generator = Mock()
        self.generator.manual_seed.return_value = self.generator
        torch = SimpleNamespace(
            device=lambda value: SimpleNamespace(type=value),
            cuda=SimpleNamespace(is_available=lambda: False),
            Generator=Mock(return_value=self.generator),
            inference_mode=nullcontext,
            amp=SimpleNamespace(autocast=lambda *args, **kwargs: nullcontext()),
            float16="float16",
        )
        sdm = SimpleNamespace(TableTensor=Table, models=SimpleNamespace(KumoTabular=self.constructor))
        self.patch = patch("enedis.prediction.models._load_kumo", return_value=(torch, sdm))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_cutoff_mask_latest_context_and_no_input_mutation(self):
        before = self.df.copy(deep=True)
        df = self.df.iloc[::-1]
        model = KumoTabular_model(df, as_of=self.index[5], context_size=3)
        x, y = self.backend.fit.call_args.args
        self.assertEqual(x.data["x"].tolist(), [1., 3., 4.])
        self.assertEqual(y.data["target"].tolist(), [1., 3., 4.])
        self.assertEqual(y.stypes, {"target": "numerical"})
        self.assertNotIn("target", x.data)
        self.assertEqual(x.stypes["season"], "categorical")
        self.assertEqual(model.n_available_, 4)
        self.assertEqual(model.n_context_, 3)
        pd.testing.assert_index_equal(model.context_index_, self.index[[1, 3, 4]])
        pd.testing.assert_frame_equal(self.df, before)
        self.assertEqual(self.constructor.call_args.kwargs["task"], "regression")
        self.backend.eval.assert_called_once()

    def test_batch_prediction_uses_median_and_does_not_refit(self):
        model = KumoTabular_model(self.df, batch_size=2)
        query = self.df.drop(columns="target")[["season", "x"]]
        before = query.copy(deep=True)
        result = predict(model, query)
        np.testing.assert_array_equal(result, self.df.x * 2)
        self.assertEqual(self.backend.predict.call_count, 4)
        self.backend.fit.assert_called_once()
        pd.testing.assert_index_equal(result.index, query.index)
        pd.testing.assert_frame_equal(query, before)
        self.assertEqual(model.predict(query.iloc[:0]).shape, (0,))

    def test_refit_reuses_weights_and_replaces_context(self):
        model = KumoTabular_model(self.df)
        model.fit(self.df[["x", "season"]].iloc[:2], self.df.target.iloc[:2])
        self.constructor.assert_called_once()
        self.backend.clear.assert_called_once()
        self.assertEqual(model.n_context_, 2)
        self.assertEqual(self.backend.fit.call_count, 2)

    def test_features_can_be_selected_explicitly(self):
        model = KumoTabular_model(self.df.assign(metadata="unused"), feature_columns=["x"])
        self.assertEqual(model.feature_names_in_.tolist(), ["x"])

    def test_future_values_cannot_affect_context(self):
        changed = self.df.copy()
        changed.loc[changed.index >= self.index[4], ["x", "target"]] = np.inf
        KumoTabular_model(changed, as_of=self.index[4])
        x, y = self.backend.fit.call_args.args
        self.assertEqual(x.data.x.tolist(), [0., 1., 3.])
        self.assertTrue(np.isfinite(y.data.target).all())

    def test_invalid_target_alignment_features_and_parameters(self):
        X, y = self.df[["x", "season"]], self.df.target
        invalid = [
            (X, y.iloc[::-1], {}), (X, y.fillna(np.inf), {}),
            (X, y.astype("string"), {}), (self.df, y, {}),
            (X, y * np.nan, {}), (X, y, {"context_size": 1}),
            (X, y, {"num_estimators": 0}), (X, y, {"batch_size": True}),
            (X, y, {"size": "huge"}), (X, y, {"random_state": 1.5}),
            (X.assign(x=np.inf), y, {}),
            (X.assign(date=self.index), y, {}),
        ]
        for features, target, options in invalid:
            with self.subTest(options=options, target_dtype=target.dtype):
                with self.assertRaises(ValueError):
                    KumoTabularRegressor(**options).fit(features, target)

    def test_predict_before_fit_and_after_failed_refit(self):
        with self.assertRaises(NotFittedError):
            KumoTabularRegressor().predict(self.df[["x"]])
        model = KumoTabular_model(self.df)
        with self.assertRaises(ValueError):
            model.fit(self.df[["x"]], self.df.target * np.nan)
        with self.assertRaises(NotFittedError):
            model.predict(self.df[["x", "season"]])

    def test_cutoff_and_factory_schema_rejected(self):
        for options in ({"as_of": "2025-01-01"}, {"feature_columns": ["x", "target"]},
                        {"feature_columns": ["absent"]}, {"feature_columns": ["x", "x"]}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                KumoTabular_model(self.df, **options)

    def test_sklearn_clone_keeps_configuration_unfitted(self):
        model = KumoTabular_model(self.df, context_size=None, num_estimators=2)
        copied = clone(model)
        self.assertEqual(copied.get_params(), model.get_params())
        with self.assertRaises(NotFittedError):
            copied.predict(self.df[["x", "season"]])


if __name__ == "__main__":
    unittest.main()
