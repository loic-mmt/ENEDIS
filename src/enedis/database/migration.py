"""Migration explicite ; controle seul par defaut, PostgreSQL 16+."""
from psycopg import sql
from .definitions import CSV_TYPES

def migrate_types(db, apply=False, tables=None):
    if db.connection.info.server_version < 160000:
        raise ValueError("PostgreSQL 16 minimum requis.")
    selected = list(CSV_TYPES) if tables is None else tables
    if set(selected) - set(CSV_TYPES):
        raise ValueError("Table inconnue.")
    for table in selected:
        with db.connection.transaction():
            db.connection.execute("SET LOCAL lock_timeout = '5s'")
            db.connection.execute("SET LOCAL DateStyle = 'ISO, YMD'")
            db.connection.execute("SET LOCAL TimeZone = 'UTC'")
            existing = dict(db.connection.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s", (db.schema, table)))
            changes = {}
            for column, target in CSV_TYPES[table].items():
                if column not in existing:
                    continue
                expected = {"timestamptz": "timestamp with time zone"}.get(target, target)
                if existing[column] == expected:
                    continue
                if existing[column] != "text":
                    raise ValueError(f"{table}.{column}: type inattendu")
                if target != "text":
                    changes[column] = target
            if not changes:
                print(f"{table}: absente ou deja conforme.", flush=True)
                continue
            qualified = sql.Identifier(db.schema, table)
            if apply:
                db.connection.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(qualified))
            checks = [sql.SQL("count(*) FILTER (WHERE {} IS NOT NULL AND NOT pg_input_is_valid({}, {}))").format(
                sql.Identifier(c), sql.Identifier(c), sql.Literal(t)) for c,t in changes.items()]
            invalid = db.connection.execute(sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(", ").join(checks), qualified)).fetchone()
            problems = {c:n for c,n in zip(changes,invalid) if n}
            if problems:
                raise ValueError(f"{table}: valeurs non convertibles: {problems}")
            print(f"{table}: {len(changes)} conversions valides.", flush=True)
            if not apply:
                continue
            counts = sql.SQL(", ").join([sql.SQL("count(*)")] + [
                sql.SQL("count({})").format(sql.Identifier(c)) for c in changes])
            query = sql.SQL("SELECT {} FROM {}").format(counts, qualified)
            before = db.connection.execute(query).fetchone()
            clauses = [sql.SQL("ALTER COLUMN {} TYPE {} USING {}::{}").format(
                sql.Identifier(c),sql.SQL(t),sql.Identifier(c),sql.SQL(t)) for c,t in changes.items()]
            db.connection.execute(sql.SQL("ALTER TABLE {} {}").format(qualified,sql.SQL(", ").join(clauses)))
            if before != db.connection.execute(query).fetchone():
                raise ValueError("Comptages modifies : annulation.")
            print(f"{table}: migration validee, {before[0]} lignes et NULL conserves.", flush=True)
