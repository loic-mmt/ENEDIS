"""Controle par defaut ; --apply convertit les tables existantes."""
import argparse
from enedis.database import Database
from enedis.database.migration import migrate_types

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--table", action="append")
    parser.add_argument("--schema", default="donnees")
    args = parser.parse_args()
    with Database(schema=args.schema) as db:
        migrate_types(db, apply=args.apply, tables=args.table)

if __name__ == "__main__":
    main()
