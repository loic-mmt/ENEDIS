"""Point d'entrée facultatif ; le code réutilisable est dans enedis.database."""
import argparse
from psycopg.conninfo import make_conninfo
from pathlib import Path

from enedis.database import Database, create_database, import_existing_data, create_source_indexes

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--schema", default="donnees")
    parser.add_argument("--create-database", metavar="NOM", help="Création explicite avec droits CREATEDB")
    parser.add_argument("--admin-dsn", default="dbname=postgres", help="Connexion administrative (sans mot de passe dans la commande)")
    parser.add_argument("--import-all", action="store_true", help="Importer réellement les fichiers CSV/Parquet et documents")
    parser.add_argument("--force", action="store_true", help="Remplacer aussi les fichiers inchangés")
    args = parser.parse_args()
    if args.create_database:
        create_database(args.create_database, args.admin_dsn)
    # La connexion aux données utilise PGDATABASE ; le nom doit correspondre.
    with Database(dsn=make_conninfo(dbname=args.create_database) if args.create_database else "", schema=args.schema) as db:
        db.initialize()
        if args.import_all:
            for result in import_existing_data(db, args.raw, force=args.force):
                print(result, flush=True)
            create_source_indexes(db)
        else:
            print("Connexion et espaces de rangement prêts. Aucun fichier importé.")


if __name__ == "__main__":
    main()
