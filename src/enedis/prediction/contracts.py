from dataclasses import dataclass
from typing import Literal

import pandas as pd

from .utils import check_choice, check_dataframe, check_integer, check_numeric

# Colonnes attendues ; les features supplémentaires restent autorisées.
HISTORY_COLUMNS = ("code_commune", "annee", "consommation_mwh", "puissance_pv_mw")
TARGET_COLUMNS = ("consommation_mwh", "puissance_pv_mw")


@dataclass(frozen=True)
class PredictionRequest:
    target: Literal["consommation_mwh", "puissance_pv_mw"]
    origin_year: int
    horizon: int

    def __post_init__(self):
        # Les annotations seules ne valident pas les valeurs reçues.
        check_choice(self.target, TARGET_COLUMNS, "target")
        check_integer(self.origin_year, "origin_year", strict=True)
        check_integer(self.horizon, "horizon", minimum=1, strict=True)


def validate_history(df: pd.DataFrame) -> None:
    """Validate the annual commune history without modifying it.

    Required columns: code_commune (nonempty text), annee (integer), and both
    numeric targets (missing values allowed). Extra feature columns are allowed.
    Commune/year pairs must be unique, with increasing years within each commune.
    Cutoff validation is handled separately by utils.verify_last_date.
    """
    # Vérifier la structure avant d'accéder aux colonnes.
    check_dataframe(df, "Historique", required=HISTORY_COLUMNS, nonempty=True)

    # Garder les codes en texte pour préserver les zéros initiaux.
    codes = df["code_commune"]
    if not codes.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise ValueError("code_commune doit contenir des textes non vides et non manquants.")

    # Une année entière et renseignée pour chaque observation.
    years = df["annee"]
    if years.isna().any() or not pd.api.types.is_integer_dtype(years.dtype):
        raise ValueError("annee doit contenir des entiers non manquants.")
    if not years.between(1, 9999).all():
        raise ValueError("annee doit être comprise entre 1 et 9999.")

    # Autoriser les cibles manquantes, mais refuser les valeurs non numériques ou infinies.
    for target in TARGET_COLUMNS:
        check_numeric(df[target], target)

    # Une seule observation par commune et par année.
    if df.duplicated(["code_commune", "annee"]).any():
        raise ValueError("Doublons sur (code_commune, annee).")

    # Vérifier l'ordre dans chaque commune, sans trier le DataFrame.
    ordered = df.groupby("code_commune", sort=False, observed=True)["annee"].apply(
        lambda values: values.is_monotonic_increasing
    )
    if not ordered.all():
        raise ValueError("Les années doivent être en ordre croissant pour chaque commune.")
