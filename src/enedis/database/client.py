"""SQL encapsulé ; aucune connexion n'est ouverte au chargement du module."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

# Types acceptés dans les définitions fournies par les utilisateurs.
TYPES = {
    "text", "integer", "bigint", "numeric", "double precision", "boolean",
    "date", "timestamp", "timestamptz", "jsonb", "bytea",
}
RESERVED = {"_source_file", "_imported_at"}


def identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise ValueError(f"Nom SQL invalide : {name!r}. Utiliser lettres minuscules et underscores.")
    return name


def sql_name(name):
    """Nom stable, sans accents, compatible avec la limite PostgreSQL."""
    value = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_") or "colonne"
    if value[0].isdigit():
        value = "c_" + value
    if len(value) > 63:
        value = value[:50] + "_" + hashlib.sha256(str(name).encode()).hexdigest()[:12]
    return identifier(value)


def column_mapping(names):
    result = {name: sql_name(name) for name in names}
    if len(result) != len(names) or len(set(result.values())) != len(result):
        raise ValueError("Des colonnes ont des noms identiques après normalisation ; les renommer explicitement.")
    if RESERVED.intersection(result.values()):
        raise ValueError("Une colonne source utilise un nom réservé à la provenance.")
    return result


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_database(name="enedis", admin_dsn="dbname=postgres"):
    """Créer la base si absente. Le compte administrateur doit avoir CREATEDB.

    Les paramètres non fournis sont lus dans les variables PostgreSQL PG*.
    Cette fonction n'installe ni PostgreSQL ni PostGIS et ne crée pas de rôle.
    """
    identifier(name)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtext(%s))", ("create_database:" + name,))
        try:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", ("create_database:" + name,))


class Database:
    """Connexion PostgreSQL. Utiliser `with Database() as db:` pour la fermer."""

    def __init__(self, dsn="", schema="donnees"):
        self.schema = identifier(schema)
        if schema in {"pg_catalog", "information_schema", "database_meta"}:
            raise ValueError("Choisir un schéma de données distinct des schémas système et de suivi.")
        self.connection = psycopg.connect(dsn, autocommit=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.connection.close()

    def initialize(self):
        with self.connection.transaction():
            self.connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            self.connection.execute("CREATE SCHEMA IF NOT EXISTS database_meta")
            self.connection.execute("""CREATE TABLE IF NOT EXISTS database_meta.fichier (
                schema_name text NOT NULL, table_name text NOT NULL, source_file text NOT NULL,
                sha256 text NOT NULL, rows_count bigint NOT NULL, imported_at timestamptz NOT NULL,
                columns_mapping jsonb NOT NULL,
                PRIMARY KEY (schema_name, table_name, source_file)
            )""")

    def create_table(self, name, columns):
        """Créer ou ajouter des colonnes sans supprimer les données existantes.

        `columns` est un dictionnaire {nom: type}. Les nouvelles colonnes sont
        NULL sur les anciennes lignes. Un changement de type exige une migration.
        """
        identifier(name)
        if not columns:
            raise ValueError("Fournir au moins une colonne.")
        for column, kind in columns.items():
            identifier(column)
            if column in RESERVED or kind not in TYPES:
                raise ValueError(f"Colonne réservée ou type non accepté : {column} / {kind}")
        self.initialize()
        qualified = sql.Identifier(self.schema, name)
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.schema + "." + name,))
            self.connection.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} "
                "(_source_file text, _imported_at timestamptz)").format(qualified))
            existing = dict(self.connection.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s", (self.schema, name)
            ).fetchall())
            aliases = {"timestamptz": "timestamp with time zone", "timestamp": "timestamp without time zone"}
            for column, kind in columns.items():
                if column in existing:
                    if existing[column] != aliases.get(kind, kind):
                        raise ValueError(f"Type incompatible pour {name}.{column} : {existing[column]} → {kind}. "
                                         "Aucune conversion automatique.")
                    continue
                self.connection.execute(sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                    qualified, sql.Identifier(column), sql.SQL(kind)))
            # Index utile lors du remplacement transactionnel d'un fichier.
            index_name = sql_name(name + "_source_file_idx")
            self.connection.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (_source_file)").format(
                sql.Identifier(index_name), qualified))

    add_columns = create_table

    def configure_table(self, name, columns, indexes=(), required=()):
        """Create/extend a table atomically using Python definitions."""
        with self.connection.transaction():
            self.create_table(name, columns)
            for column in required:
                identifier(column)
                if column not in columns:
                    raise ValueError("Required column missing from definition.")
                self.connection.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN {} SET NOT NULL").format(
                    sql.Identifier(self.schema, name), sql.Identifier(column)))
            for spec in indexes:
                fields = spec["columns"]
                if not fields or any(c not in columns for c in fields):
                    raise ValueError("Invalid index columns.")
                unique = spec.get("unique", False)
                index_name = sql_name(name + "_" + "_".join(fields) + ("_uniq" if unique else "_idx"))
                self.connection.execute(sql.SQL("CREATE {} INDEX IF NOT EXISTS {} ON {} ({})").format(
                    sql.SQL("UNIQUE" if unique else ""), sql.Identifier(index_name),
                    sql.Identifier(self.schema, name),
                    sql.SQL(", ").join(sql.Identifier(c) for c in fields)))

    def read_table(self, name, columns=None, filters=None, limit=1000):
        """Retourner un DataFrame ; filtres d'égalité paramétrés, LIMIT par défaut.

        Passer limit=None explicitement pour charger toute une table en mémoire.
        """
        import pandas as pd
        identifier(name)
        selection = sql.SQL("*") if columns is None else sql.SQL(", ").join(
            sql.Identifier(identifier(c)) for c in columns)
        if columns is not None and not columns:
            raise ValueError("La liste de colonnes ne doit pas être vide.")
        query = sql.SQL("SELECT {} FROM {}").format(selection, sql.Identifier(self.schema, name))
        parameters = []
        clauses = []
        for column, value in (filters or {}).items():
            column = sql.Identifier(identifier(column))
            clauses.append(sql.SQL("{} IS NULL").format(column) if value is None
                           else sql.SQL("{} = %s").format(column))
            if value is not None:
                parameters.append(value)
        if clauses:
            query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError("limit doit être un entier positif ou None.")
            query += sql.SQL(" LIMIT %s")
            parameters.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return pd.DataFrame(cursor.fetchall(), columns=[c.name for c in cursor.description])

    def import_csv(self, path, table, types=None, delimiter=None, force=False):
        """CSV en flux. Types par défaut : texte ; blancs → NULL, jamais zéro.

        `types` utilise les noms SQL normalisés, par exemple {"annee": "integer"}.
        Les marqueurs non vides comme N/A restent des valeurs sources.
        """
        path = Path(path).resolve()
        with path.open(encoding="utf-8-sig", newline="") as stream:
            if delimiter is None:
                sample = stream.read(65536)
                stream.seek(0)
                try:
                    delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
                except csv.Error as error:
                    raise ValueError("Séparateur indéterminé ; fournir delimiter explicitement.") from error
            reader = csv.reader(stream, delimiter=delimiter)
            header = next(reader, None)
            if not header:
                raise ValueError(f"CSV sans en-tête : {path}")
            mapping = column_mapping(header)
            columns = {name: "text" for name in mapping.values()}
            if types:
                if set(types) - set(columns):
                    raise ValueError("Le dictionnaire de types contient des colonnes absentes du CSV.")
                columns.update(types)
            def rows():
                for number, row in enumerate(reader, start=2):
                    if len(row) != len(header):
                        raise ValueError(f"{path.name}, enregistrement {number} : nombre de champs incorrect.")
                    yield [None if not value.strip() else value for value in row]
            return self._import_rows(path, table, mapping, columns, rows(), force)

    def import_parquet(self, path, table, dataset_root=None, force=False, batch_size=64000):
        import pyarrow as pa
        import pyarrow.dataset as ds
        path = Path(path).resolve()
        root = Path(dataset_root).resolve() if dataset_root else path.parent
        dataset = ds.dataset([str(path)], format="parquet", partitioning="hive", partition_base_dir=str(root))
        mapping = column_mapping(dataset.schema.names)
        def postgres_type(kind):
            if pa.types.is_dictionary(kind):
                return postgres_type(kind.value_type)
            if pa.types.is_boolean(kind): return "boolean"
            if pa.types.is_integer(kind): return "numeric" if pa.types.is_uint64(kind) else "bigint"
            if pa.types.is_floating(kind): return "double precision"
            if pa.types.is_decimal(kind): return "numeric"
            if pa.types.is_timestamp(kind): return "timestamptz" if kind.tz else "timestamp"
            if pa.types.is_date(kind): return "date"
            if pa.types.is_binary(kind) or pa.types.is_large_binary(kind): return "bytea"
            if pa.types.is_string(kind) or pa.types.is_large_string(kind) or pa.types.is_null(kind): return "text"
            raise ValueError(f"Type Parquet à définir explicitement avant import : {kind}")
        columns = {mapping[field.name]: postgres_type(field.type) for field in dataset.schema}
        def rows():
            for batch in dataset.to_batches(batch_size=batch_size):
                for row in batch.to_pylist():
                    yield [row[key] for key in mapping]
        return self._import_rows(path, table, mapping, columns, rows(), force)

    def import_json_document(self, path, table="documents_source", force=False):
        path = Path(path).resolve()
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return self._import_rows(path, table, {"document": "document"},
                                 {"document": "jsonb"}, [(Jsonb(value),)], force)

    def import_text_document(self, path, table="documents_texte", force=False):
        path = Path(path).resolve()
        return self._import_rows(path, table, {"contenu": "contenu"},
                                 {"contenu": "text"}, [(path.read_text(encoding="utf-8-sig"),)], force)

    def _import_rows(self, path, table, mapping, columns, rows, force):
        before = path.stat()
        digest = fingerprint(path)
        # DDL et données font partie de la même transaction pour ce fichier.
        with self.connection.transaction():
            self.create_table(table, columns)
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.schema + "." + table,))
            key = (self.schema, table, str(path))
            old = self.connection.execute("SELECT sha256, columns_mapping, rows_count FROM database_meta.fichier "
                "WHERE schema_name=%s AND table_name=%s AND source_file=%s", key).fetchone()
            if old and old[0] == digest and old[1] == mapping and not force:
                return {"table": table, "file": str(path), "status": "deja_importe", "rows": old[2]}
            self.connection.execute(sql.SQL("DELETE FROM {} WHERE _source_file=%s").format(
                sql.Identifier(self.schema, table)), (str(path),))
            timestamp = datetime.now(timezone.utc)
            query = sql.SQL("COPY {} ({}) FROM STDIN").format(
                sql.Identifier(self.schema, table), sql.SQL(", ").join(
                    sql.Identifier(c) for c in [*columns, "_source_file", "_imported_at"]))
            count = 0
            with self.connection.cursor() as cursor:
                with cursor.copy(query) as copy:
                    for row in rows:
                        copy.write_row((*row, str(path), timestamp))
                        count += 1
            after = path.stat()
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise ValueError("Fichier modifié pendant l'import : écritures annulées.")
            self.connection.execute("""INSERT INTO database_meta.fichier
                (schema_name,table_name,source_file,sha256,rows_count,imported_at,columns_mapping)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (schema_name,table_name,source_file) DO UPDATE SET
                sha256=excluded.sha256,rows_count=excluded.rows_count,
                imported_at=excluded.imported_at,columns_mapping=excluded.columns_mapping""",
                (*key, digest, count, timestamp, Jsonb(mapping)))
        return {"table": table, "file": str(path), "status": "importe", "rows": count}
