"""Importer la consommation sans imputation ni agrégation.

Aucun effet lors d'un simple import du module. L'exécution demande la création
préalable de la base et des tables ; la connexion utilise les variables PG*.
"""
import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv"
MAPPING = ROOT / "sql/module_1/colonnes_consommation.json"
VERSION = "consommation-v1"


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(row, mapping, number):
    for field in mapping:
        raw = row[field["source"]].strip()
        kind = field["type"]
        if not raw or kind == "text":
            continue
        try:
            value = Decimal(raw)
            if not value.is_finite():
                raise ValueError("nombre non fini")
            if kind in ("integer", "bigint") and value != value.to_integral_value():
                raise ValueError("entier attendu")
        except (InvalidOperation, ValueError) as error:
            raise ValueError(
                f"Enregistrement {number}, colonne {field['source']} : {raw!r} invalide."
            ) from error


def import_file(source):
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    before = source.stat()
    digest = fingerprint(source)
    expected_headers = [field["source"] for field in mapping]
    # psycopg/libpq lit PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD ou .pgpass.
    # Tout l'import est transactionnel : une erreur annule toutes ses écritures.
    with psycopg.connect("") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("consommation:" + digest,))
            cur.execute(
                "SELECT id_import FROM meta.import_fichier WHERE jeu_donnees=%s "
                "AND empreinte_sha256=%s AND version_pipeline=%s",
                ("consommation", digest, VERSION),
            )
            existing = cur.fetchone()
            if existing:
                print(f"Fichier déjà importé : import {existing[0]}. Aucune ligne ajoutée.")
                return
            cur.execute(
                "INSERT INTO meta.import_fichier "
                "(jeu_donnees, nom_fichier, empreinte_sha256, version_pipeline, nombre_lignes) "
                "VALUES (%s,%s,%s,%s,0) RETURNING id_import",
                ("consommation", str(source.resolve()), digest, VERSION),
            )
            import_id = cur.fetchone()[0]
            total = 0
            with source.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != expected_headers:
                    raise ValueError("Les colonnes CSV diffèrent du dictionnaire attendu ; import annulé.")
                with cur.copy(
                    "COPY staging.observation "
                    "(id_import, numero_enregistrement, donnees_source) FROM STDIN"
                ) as copy:
                    for number, row in enumerate(reader, start=2):
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError(f"Enregistrement {number} : nombre de champs incorrect.")
                        validate(row, mapping, number)
                        copy.write_row((import_id, number, Jsonb(row)))
                        total += 1
                        if total % 100_000 == 0:
                            print(f"{total:,} lignes sources chargées, validation finale à venir…", flush=True)
            if total == 0:
                raise ValueError("Fichier vide : import annulé.")
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Le fichier a changé pendant sa lecture : import annulé.")
            columns = [sql.Identifier(field["colonne"]) for field in mapping]
            expressions = []
            for field in mapping:
                value = sql.SQL("NULLIF(btrim(donnees_source ->> {}), '')").format(sql.Literal(field["source"]))
                kind = field["type"]
                if kind in ("integer", "bigint"):
                    value = sql.SQL("({})::numeric::{}").format(value, sql.SQL(kind))
                elif kind == "numeric":
                    value = sql.SQL("({})::numeric").format(value)
                elif kind != "text":
                    raise ValueError("Type non pris en charge dans le dictionnaire.")
                expressions.append(value)
            statement = sql.SQL(
                "INSERT INTO core.consommation_annuelle (id_observation, {}) "
                "SELECT id_observation, {} FROM staging.observation WHERE id_import = %s"
            ).format(sql.SQL(", ").join(columns), sql.SQL(", ").join(expressions))
            cur.execute(statement, (import_id,))
            if cur.rowcount != total:
                raise ValueError("Comptage incohérent entre données sources et table typée.")
            cur.execute("UPDATE meta.import_fichier SET nombre_lignes=%s WHERE id_import=%s", (total, import_id))
    print(f"Import {import_id} validé : {total:,} lignes. Aucune imputation effectuée.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    try:
        import_file(args.source)
    except (OSError, ValueError, psycopg.Error):
        # Ne pas afficher la chaîne de connexion ni les secrets.
        print("Échec : import non validé. Les écritures de cet import sont annulées.", flush=True)
        raise


if __name__ == "__main__":
    main()
