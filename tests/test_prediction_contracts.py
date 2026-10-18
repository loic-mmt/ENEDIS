from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from enedis.prediction.contracts import validate_history


class HistoryContractTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "code_commune": ["01001", "2A004", "01001", "2A004"],
            "annee": [2023, 2023, 2024, 2024],
            "consommation_mwh": [100., np.nan, 120., 0.],
            "puissance_pv_mw": [0., 1., 2., 3.],
            "feature_extra": [1, 2, 3, 4],
        })

    def test_valid_interleaved_communes_and_no_mutation(self):
        before = self.frame.copy(deep=True)
        self.assertIsNone(validate_history(self.frame))
        pd.testing.assert_frame_equal(self.frame, before)

    def test_nullable_types_and_all_missing_target(self):
        frame = self.frame.astype({"annee": "Int64", "consommation_mwh": "Float64"})
        frame["puissance_pv_mw"] = None
        validate_history(frame)

    def test_missing_column_and_empty_history(self):
        with self.assertRaisesRegex(ValueError, "absentes"):
            validate_history(self.frame.drop(columns="annee"))
        with self.assertRaisesRegex(ValueError, "vide"):
            validate_history(self.frame.iloc[:0])
        with self.assertRaises(TypeError):
            validate_history([])

    def test_duplicate_columns(self):
        with self.assertRaisesRegex(ValueError, "colonnes dupliqués"):
            validate_history(pd.concat([self.frame, self.frame[["annee"]]], axis=1))

    def test_invalid_commune_codes(self):
        for value in [None, 1001, "", "   "]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "code_commune"):
                validate_history(self.frame.assign(code_commune=[value, "2A004", "01001", "2A004"]))

    def test_invalid_years(self):
        for years in [[2023., 2023., 2024., 2024.], ["2023"] * 4,
                      [True] * 4, [2023, None, 2024, 2024], [0, 2023, 2024, 2024]]:
            with self.subTest(years=years), self.assertRaisesRegex(ValueError, "annee"):
                validate_history(self.frame.assign(annee=years))

    def test_invalid_targets(self):
        for values in [["100"] * 4, [True] * 4, [np.inf] * 4, [1j] * 4]:
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "consommation_mwh"):
                validate_history(self.frame.assign(consommation_mwh=values))

    def test_duplicate_commune_year(self):
        with self.assertRaisesRegex(ValueError, "Doublons"):
            validate_history(pd.concat([self.frame, self.frame.iloc[:1]], ignore_index=True))

    def test_year_order_checked_within_each_commune(self):
        with self.assertRaisesRegex(ValueError, "ordre croissant"):
            validate_history(self.frame.iloc[[2, 1, 0, 3]])


if __name__ == "__main__":
    unittest.main()
