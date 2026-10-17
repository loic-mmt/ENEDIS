from numbers import Integral

import pandas as pd


def verify_last_date(df: pd.DataFrame, date_column: str, cutoff) -> None:
    """Reject empty histories, invalid dates and observations after cutoff.

    Accept integer years (or four-digit year strings) with an integer/year-string
    cutoff, or datetime values with a datetime-like cutoff. For datetime values,
    explicit offsets are converted to UTC; naive values are interpreted as UTC.
    Does not filter, sort or modify the input. Older histories remain valid.
    """
    if date_column not in df.columns:
        raise ValueError(f"Colonne temporelle absente : {date_column}")
    if df.empty:
        raise ValueError("Historique vide.")
    dates = df[date_column]
    if not isinstance(dates, pd.Series):
        raise ValueError(f"Colonne temporelle dupliquée : {date_column}")
    if dates.isna().any():
        raise ValueError("Dates manquantes dans l'historique.")

    year_strings = dates.astype("string").str.fullmatch(r"\d{4}").all()
    if pd.api.types.is_integer_dtype(dates.dtype) or year_strings:
        years = pd.to_numeric(dates, errors="raise")
        if not years.between(1, 9999).all():
            raise ValueError("Année invalide dans l'historique.")
        if isinstance(cutoff, bool) or not (
            isinstance(cutoff, Integral)
            or isinstance(cutoff, str) and len(cutoff) == 4 and cutoff.isdigit()
        ):
            raise ValueError("Pour des années, cutoff doit être une année entière.")
        limit = int(cutoff)
        if not 1 <= limit <= 9999:
            raise ValueError("Année limite invalide.")
        latest = years.max()
    else:
        if pd.api.types.is_numeric_dtype(dates.dtype) or isinstance(cutoff, (Integral, bool)):
            raise ValueError("Format temporel incompatible : utiliser des années entières ou des dates.")
        try:
            parsed = pd.to_datetime(dates, format="mixed", utc=True, errors="raise")
            limit = pd.to_datetime(cutoff, utc=True, errors="raise")
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError("Date ou limite temporelle invalide.") from error
        if parsed.isna().any() or not isinstance(limit, pd.Timestamp) or pd.isna(limit):
            raise ValueError("Date ou limite temporelle manquante ou invalide.")
        latest = parsed.max()
    if latest > limit:
        raise ValueError(f"Données futures présentes : {latest} > {limit}.")
