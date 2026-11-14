from numbers import Integral, Real

import numpy as np
import pandas as pd


def check_integer(value, name, *, minimum=None, maximum=None, strict=False) -> None:
    """Accept integers (including NumPy integers), never booleans.

    strict=True accepts Python int only, for existing public contracts.
    """
    valid_type = type(value) is int if strict else isinstance(value, Integral)
    if isinstance(value, bool) or not valid_type:  # bool hérite de int en Python.
        raise ValueError(f"{name} doit être un entier.")

    if minimum is not None and value < minimum:
        raise ValueError(f"{name} doit être un entier supérieur ou égal à {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} doit être un entier inférieur ou égal à {maximum}.")


def check_real(value, name, *, minimum=None, maximum=None, positive=False) -> None:
    """Check a finite real scalar and optional bounds; reject booleans."""
    if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"{name} doit être un nombre réel fini.")

    if positive and value <= 0:
        raise ValueError(f"{name} doit être strictement positif.")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{name} doit être compris entre {minimum} et {maximum}.")


def check_choice(value, choices, name) -> None:
    """Check membership without converting the supplied value."""
    try:
        valid = value in choices
    except (TypeError, ValueError):
        valid = False

    if not valid:
        raise ValueError(f"{name} doit être choisi parmi {tuple(choices)} ; reçu : {value!r}.")


def check_collection(values, name, *, choices=None, integers=False, minimum=None,
                     strict=False, allow_empty=False) -> list:
    """Materialize a non-string iterable; validate items and reject duplicates."""
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} doit être une collection, pas une chaîne.")

    try:
        items = list(values)
    except TypeError as error:
        raise ValueError(f"{name} doit être une collection.") from error

    if not items and not allow_empty:
        raise ValueError(f"{name} ne doit pas être vide.")

    for item in items:
        if integers:
            check_integer(item, name, minimum=minimum, strict=strict)
        if choices is not None:
            check_choice(item, choices, name)

    try:
        unique = len(set(items)) == len(items)
    except TypeError as error:
        raise ValueError(f"{name} doit contenir des éléments simples et distincts.") from error

    if not unique:
        raise ValueError(f"{name} doit contenir des éléments distincts.")

    return items


def check_dataframe(df, name="Données", *, required=(), nonempty=False,
                    min_columns=0, string_columns=False, type_error=TypeError) -> None:
    """Check table structure without changing its contents or order."""
    if not isinstance(df, pd.DataFrame):
        raise type_error(f"{name} doit être un DataFrame pandas.")

    if not df.columns.is_unique:
        raise ValueError(f"Noms de colonnes dupliqués dans {name}.")

    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Colonnes obligatoires absentes dans {name} : {', '.join(missing)}")

    if nonempty and len(df) == 0:
        raise ValueError(f"{name} vide.")
    if df.shape[1] < min_columns:
        raise ValueError(f"{name} doit contenir au moins {min_columns} colonne(s).")
    if string_columns and not all(isinstance(column, str) for column in df.columns):
        raise ValueError(f"Les noms de colonnes de {name} doivent être des chaînes.")


def check_column(df, column, name="Colonne") -> None:
    """Require one named column, refusing missing or duplicated selections."""
    if not isinstance(column, str) or column not in df.columns:
        raise ValueError(f"{name} absente ou invalide : {column}")
    if not isinstance(df[column], pd.Series):
        raise ValueError(f"{name} dupliquée : {column}")


def check_finite(values, name, *, allow_missing=False) -> None:
    """Check numeric scalars/arrays; only NaN may represent missing values."""
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values) | (np.isnan(values) if allow_missing else False)
    if not valid.all():
        raise ValueError(f"{name} contient des valeurs non finies.")


def check_numeric(values: pd.Series, name=None, *, allow_missing=True,
                  allow_empty=True, allow_bool=False, allow_complex=False,
                  finite=True, minimum=None, integer=False) -> None:
    """Check a numeric Series; optionally allow an entirely missing column.

    No text-to-number coercion, filling or mutation is performed.
    """
    name = name if name is not None else values.name
    observed = values.dropna()

    if not allow_missing and values.isna().any():
        raise ValueError(f"{name} contient des valeurs manquantes.")
    if allow_empty and observed.empty:
        return

    dtype = values.dtype
    if (not pd.api.types.is_numeric_dtype(dtype)
            or not allow_bool and pd.api.types.is_bool_dtype(dtype)
            or not allow_complex and pd.api.types.is_complex_dtype(dtype)):
        raise ValueError(f"{name} doit contenir des nombres.")

    numbers = observed.to_numpy(dtype=complex if pd.api.types.is_complex_dtype(dtype) else float)
    if finite:
        # Keep complex values intact when a legacy caller explicitly allows them.
        if not np.isfinite(numbers).all():
            raise ValueError(f"{name} contient des valeurs non finies.")

    if minimum is not None and (numbers < minimum).any():
        raise ValueError(f"{name} doit contenir des valeurs supérieures ou égales à {minimum}.")
    if integer and (numbers % 1 != 0).any():
        raise ValueError(f"{name} doit contenir des nombres entiers.")


def check_datetime_index(index, name="Horodates", *, aware=True, unique=True,
                         ordered=False, nonempty=False, step=None, regular=False) -> None:
    """Check dates, optionally on a fixed UTC grid (DST-safe)."""
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(f"{name} doit être un DatetimeIndex.")
    if index.hasnans or aware and index.tz is None:
        raise ValueError(f"{name} doit être renseigné avec un fuseau explicite.")

    if nonempty and len(index) == 0:
        raise ValueError(f"{name} vide.")

    if unique and index.has_duplicates:
        raise ValueError(f"{name} contient des dates répétées.")
    if ordered and not index.is_monotonic_increasing:
        raise ValueError(f"{name} doit être en ordre croissant.")
    if step is not None:
        dates = index.tz_convert("UTC") if index.tz is not None else index  # Grille sans ambiguïté été/hiver.
        if not dates.equals(dates.floor(step)):
            raise ValueError(f"{name} doit être aligné sur la grille {step}.")
        if regular and len(dates) and not dates.equals(pd.date_range(dates[0], dates[-1], freq=step)):
            raise ValueError(f"{name} doit suivre une grille régulière {step}, avec les trous conservés.")


def check_timestamp(value, name="as_of", *, step=None) -> pd.Timestamp:
    """Parse one explicit-timezone timestamp and return its UTC equivalent."""
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} doit être une date avec fuseau explicite.") from error

    check_datetime_index(pd.DatetimeIndex([stamp]), name, step=step)

    return stamp.tz_convert("UTC")


def check_aligned_series(values, index, name="y") -> None:
    """Require a Series with exactly the same row labels and order."""
    if not isinstance(values, pd.Series) or not values.index.equals(index):
        raise ValueError(f"{name} doit être une Series alignée sur l'index des features.")


def check_feature_columns(X, expected=None, *, allow_empty=False) -> None:
    """Require named features and, if supplied, exactly the fitted schema."""
    check_dataframe(X, "X", min_columns=0 if allow_empty else 1, string_columns=True, type_error=ValueError)
    if expected is not None and set(X.columns) != set(expected):
        raise ValueError("Les features doivent correspondre à celles du fit.")


def check_feature_type(values: pd.Series, stype=None) -> str:
    """Infer/validate one SDK feature type, identically at fit and prediction."""
    if stype is None:
        if pd.api.types.is_numeric_dtype(values.dtype):
            stype = "numerical"
        elif (isinstance(values.dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(values.dtype)):
            stype = "categorical"
        else:
            raise ValueError(f"Feature non numérique/catégorielle : {values.name}")
    if stype == "numerical":
        check_numeric(values, f"Feature {values.name}", allow_bool=True, allow_empty=False)

    return stype


def check_regression_target(X, y) -> None:
    """Validate aligned regression labels, excluding target-as-feature leakage."""
    check_aligned_series(y, X.index)
    if y.name in X.columns:
        raise ValueError("La cible ne doit pas figurer parmi les features.")
    check_numeric(y, "Cible de régression", allow_empty=False)
    if y.notna().sum() < 2:
        raise ValueError("Au moins deux cibles observées sont nécessaires.")


def check_predictions(result, index) -> np.ndarray:
    """Normalize single-target model output; check shape, labels and numbers."""
    if isinstance(result, (pd.Series, pd.DataFrame)):
        if not result.index.equals(index):
            raise ValueError("L'index des prédictions doit correspondre à X.")

        result = result.to_numpy()

    values = np.asarray(result)
    if values.ndim == 2 and values.shape[1] == 1:
        values = values[:, 0]  # (n, 1) -> (n,) ; garder une prédiction par ligne.
    if values.ndim != 1 or len(values) != len(index):
        raise ValueError("Une prédiction par ligne est attendue (une seule cible).")
    if values.dtype.kind not in "fiu":
        raise ValueError("Les prédictions doivent être numériques.")

    check_finite(values, "Prédictions", allow_missing=True)

    return values.astype(float)


def check_reconstruction_inputs(observed, gaps):
    """Validate masked half-hourly blocks and return a UTC series and block tuples."""
    step = pd.Timedelta(minutes=30)
    if not isinstance(observed, pd.Series):
        raise ValueError("Série observée attendue avec DatetimeIndex explicite.")
    check_datetime_index(observed.index, nonempty=True, ordered=True, step="30min", regular=True)
    index = observed.index
    index = index.tz_convert("UTC")
    check_numeric(observed, "Production", allow_empty=False, minimum=0)
    values = observed.to_numpy(dtype=float, na_value=np.nan)
    required = ["gap_id", "start", "end_exclusive", "n_slots"]
    check_dataframe(gaps, "Blocs", required=required, nonempty=True, type_error=ValueError)
    if gaps["gap_id"].isna().any() or gaps["gap_id"].duplicated().any():
        raise ValueError("Identifiants de trous uniques non manquants requis.")

    series = pd.Series(values, index=index.rename("horodate"))
    blocks, used = [], set()

    for _, gap in gaps.iterrows():
        start = check_timestamp(gap["start"], "Début du trou", step="30min")
        end = check_timestamp(gap["end_exclusive"], "Fin du trou")
        length = gap["n_slots"]
        check_integer(length, "n_slots", minimum=1)
        if end - start != int(length) * step:
            raise ValueError("Durée ou bornes de trou incohérentes.")

        target = pd.date_range(start, end, freq="30min", inclusive="left", name="horodate")
        if not target.isin(index).all() or used.intersection(target):
            raise ValueError("Blocs hors série ou qui se chevauchent.")
        if series.reindex(target).notna().any():
            raise ValueError("Les cibles des trous doivent être masquées avant toute reconstruction.")
        used.update(target)
        blocks.append((gap["gap_id"], start, end, target))

    return series, blocks


def verify_last_date(df: pd.DataFrame, date_column: str, cutoff) -> None:
    """Reject empty histories, invalid dates and observations after cutoff.

    Accept integer years (or four-digit year strings) with an integer/year-string
    cutoff, or datetime values with a datetime-like cutoff. For datetime values,
    explicit offsets are converted to UTC; naive values are interpreted as UTC.
    Does not filter, sort or modify the input. Older histories remain valid.
    """
    check_column(df, date_column, "Colonne temporelle")
    if df.empty:
        raise ValueError("Historique vide.")

    dates = df[date_column]
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
