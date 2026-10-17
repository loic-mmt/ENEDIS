import pandas as pd
import numpy as np
from numbers import Integral

from .utils import verify_last_date


def persistance_baseline(
    df: pd.DataFrame, target: str, date_column: str, last_date, horizon: int
) -> np.ndarray:
    """Repeat the last observed target for `horizon` annual steps.

    Input must describe ONE commune, already ordered chronologically and limited
    to last_date by the caller. Missing targets are skipped; an entirely missing
    target produces NaN predictions. No filtering or mutation is performed.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, Integral) or horizon <= 0:
        raise ValueError("horizon doit être un entier strictement positif.")
    if not isinstance(target, str) or target not in df.columns:
        raise ValueError(f"Colonne cible absente ou invalide : {target}")
    
    verify_last_date(df, date_column, last_date)

    variable = df[target]

    if not isinstance(variable, pd.Series):
        raise ValueError(f"Colonne cible dupliquée : {target}")
    if not pd.api.types.is_numeric_dtype(variable.dtype) and variable.notna().any():
        raise ValueError(f"La cible {target} doit être numérique.")
    
    observed = variable.dropna()
    value = float(observed.iloc[-1]) if not observed.empty else np.nan

    if not observed.empty and not np.isfinite(value):
        raise ValueError("La dernière valeur observée doit être finie.")
    
    return np.full(horizon, value, dtype=float)


