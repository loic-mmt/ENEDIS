"""Reconstruire la base locale de reference"""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from enedis.database import Database, create_database, import_existing_data, create_source_indexes

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = Path(__file__).with_name("reference_base.json")

def check_files(root, reference):
    if not root.is_dir():
        raise ValueError(f"Dossier absent : {root}")
    actual = {f.relative_to(root).as_posix(): f for f in root.rglob("*")
              if f.is_file() and f.suffix.lower() in {".csv", ".parquet", ".json", ".txt"}
              and not f.name.endswith(":Zone.Identifier")}
    expected = reference["files"]
    if set(actual) != set(expected):
        raise ValueError(f"Sources differentes : manquantes={sorted(set(expected)-set(actual))}, "
                         f"supplementaires={sorted(set(actual)-set(expected))}")
    for name, f in actual.items():
        digest = hashlib.sha256()
        with f.open("rb") as stream:
            for block in iter(lambda: stream.read(8*1024*1024), b""):
                digest.update(block)
        if f.stat().st_size != expected[name]["bytes"] or digest.hexdigest() != expected[name]["sha256"]:
            raise ValueError(f"Version du fichier differente : {name}")
    print(f"Sources conformes : {len(actual)} fichiers.", flush=True)

def verify(db, ref):
    current = {}
    for table, column, kind in db.connection.execute(
        "SELECT table_name,column_name,data_type FROM information_schema.columns "
        "WHERE table_schema='donnees'"):
        current.setdefault(table,{})[column] = kind
    errors = []
    for table, expected in ref["schema"].items():
        if current.get(table) != expected:
            errors.append(f"Colonnes/types differents : {table}")
    if errors:
        raise ValueError("; ".join(errors))
    for table, expected in ref["counts"].items():
        count = db.connection.execute(sql.SQL("SELECT count(*) FROM {}").format(
            sql.Identifier("donnees",table))).fetchone()[0]
        if count != expected:
            raise ValueError(f"{table}: {count} lignes au lieu de {expected}")
        print(f"{table}: types et {count} lignes conformes.", flush=True)
    missing, zeros = db.connection.execute(
        "SELECT count(*) FILTER (WHERE conso_totale_mwh IS NULL), "
        "count(*) FILTER (WHERE conso_totale_mwh=0) FROM donnees.consommation_annuelle").fetchone()
    if (missing,zeros) != (446907,606401):
        raise ValueError(f"Consommation : NULL/zeros inattendus : {missing}/{zeros}")
    print("Base enedis conforme a la reference : types, volumes, NULL et zeros.", flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT/"data/raw")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default=os.environ.get("PGUSER","postgres"))
    parser.add_argument("--check-files", action="store_true", help="Verifier les fichiers sans connexion")
    parser.add_argument("--verify-only", action="store_true", help="Verifier la base sans import ni creation")
    args = parser.parse_args()
    ref = json.loads(REFERENCE.read_text(encoding="utf-8"))
    if not args.verify_only:
        check_files(args.raw.resolve(), ref)
    if args.check_files:
        return
    password = os.environ.get("PGPASSWORD")
    if password is None:
        password = getpass.getpass(f"Mot de passe PostgreSQL du compte {args.user} (vide si authentification locale) : ")
    base = dict(host=args.host,port=args.port,user=args.user,connect_timeout=10)
    if password:
        base["password"] = password
    admin = make_conninfo(dbname="postgres",**base)
    if not args.verify_only:
        with psycopg.connect(admin) as conn:
            if conn.info.server_version < 160000:
                raise ValueError("PostgreSQL 16 ou plus recent requis.")
        create_database("enedis",admin_dsn=admin)
    with Database(make_conninfo(dbname="enedis",**base)) as db:
        if not args.verify_only:
            db.initialize()
            # Eviter de doubler une livraison restauree ou deplacee.
            known = [r[0] for r in db.connection.execute(
                "SELECT source_file FROM database_meta.fichier WHERE schema_name='donnees'")]
            root = args.raw.resolve()
            allowed = {str((root/name).resolve()) for name in ref["files"]}
            if set(known)-allowed:
                raise ValueError("Cette base contient des imports depuis un autre chemin. "
                                 "Utiliser --verify-only ou examiner la base avant de continuer.")
            for result in import_existing_data(db,root):
                print(result,flush=True)
            create_source_indexes(db)
        verify(db,ref)

if __name__ == "__main__":
    try:
        main()
    except (ValueError,OSError,psycopg.Error) as error:
        # Ne pas afficher une chaine de connexion ou un mot de passe.
        print(f"Installation interrompue ({type(error).__name__}).")
        if isinstance(error, ValueError):
            print(str(error))
        else:
            print("Verifier serveur, compte, droits, espace disque et fichiers. Aucun secret affiche.")
        raise SystemExit(1)
