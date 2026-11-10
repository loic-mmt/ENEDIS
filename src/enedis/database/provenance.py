"""Provenance compacte avec restitution des colonnes historiques en lecture."""
from psycopg import sql

def is_compact(conn, schema, table):
    return bool(conn.execute("SELECT 1 FROM information_schema.columns WHERE "
        "table_schema=%s AND table_name=%s AND column_name='_provenance_id'",
        (schema,table)).fetchone())

def initialize_provenance(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS database_meta.provenance (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        schema_name text NOT NULL,
        table_name text NOT NULL,
        source_file text NOT NULL,
        imported_at timestamptz NOT NULL,
        UNIQUE(schema_name,table_name,source_file,imported_at)
    )""")

def provenance_id(conn,schema,table,path,timestamp):
    return conn.execute("""INSERT INTO database_meta.provenance
        (schema_name,table_name,source_file,imported_at) VALUES (%s,%s,%s,%s)
        ON CONFLICT(schema_name,table_name,source_file,imported_at)
        DO UPDATE SET source_file=excluded.source_file RETURNING id""",
        (schema,table,path,timestamp)).fetchone()[0]

def read_relation(conn,schema,table):
    """Relation SQL restituant provenance et colonnes metier, sans identifiant interne."""
    if not is_compact(conn,schema,table):
        return sql.Identifier(schema,table)
    columns=[r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=%s "
        "AND table_name=%s AND column_name<>'_provenance_id' ORDER BY ordinal_position",
        (schema,table))]
    selection=[sql.SQL("p.source_file AS _source_file"),sql.SQL("p.imported_at AS _imported_at")]
    selection += [sql.Identifier("t",c) for c in columns]
    return sql.SQL("(SELECT {} FROM {} t JOIN database_meta.provenance p "
                   "ON p.id=t._provenance_id) AS lecture").format(
        sql.SQL(", ").join(selection),sql.Identifier(schema,table))
