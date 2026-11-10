"""Migration de provenance sans changement des colonnes metier."""
from psycopg import sql
from .client import identifier, sql_name
from .provenance import is_compact, initialize_provenance, read_relation

def groups(conn, relation):
    return conn.execute(sql.SQL("SELECT _source_file,_imported_at,count(*) FROM {} "
        "GROUP BY _source_file,_imported_at ORDER BY _source_file,_imported_at").format(relation)).fetchall()

def inspect_table(conn,schema,table):
    qualified=sql.Identifier(schema,table)
    before=groups(conn,read_relation(conn,schema,table))
    if any(path is None or date is None for path,date,_ in before):
        raise ValueError(f"{table}: provenance NULL, migration refusee.")
    totals={}
    for path,date,count in before:
        totals[path]=totals.get(path,0)+count
    tracked=dict(conn.execute("SELECT source_file,rows_count FROM database_meta.fichier "
        "WHERE schema_name=%s AND table_name=%s",(schema,table)))
    if totals != {path:count for path,count in tracked.items() if count}:
        raise ValueError(f"{table}: comptages differents du suivi d'import.")
    return before

def optimize_table(conn,schema,table,apply=False):
    identifier(schema)
    identifier(table)
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='5s'")
        if apply:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(schema+"."+table,))
            conn.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(sql.Identifier(schema,table)))
        before=inspect_table(conn,schema,table)
        if is_compact(conn,schema,table):
            return {"table":table,"status":"deja_optimisee","rows":sum(r[2] for r in before)}
        if not apply:
            return {"table":table,"status":"controle_valide","rows":sum(r[2] for r in before),"provenances":len(before)}
        initialize_provenance(conn)
        qualified=sql.Identifier(schema,table)
        conn.execute(sql.SQL("INSERT INTO database_meta.provenance "
            "(schema_name,table_name,source_file,imported_at) "
            "SELECT %s,%s,_source_file,_imported_at FROM {} GROUP BY _source_file,_imported_at "
            "ON CONFLICT DO NOTHING").format(qualified),(schema,table))
        conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN _provenance_id bigint").format(qualified))
        conn.execute(sql.SQL("UPDATE {} t SET _provenance_id=p.id FROM database_meta.provenance p "
            "WHERE p.schema_name=%s AND p.table_name=%s AND p.source_file=t._source_file "
            "AND p.imported_at=t._imported_at").format(qualified),(schema,table))
        mismatch=conn.execute(sql.SQL("SELECT count(*) FROM {} t LEFT JOIN database_meta.provenance p "
            "ON p.id=t._provenance_id WHERE p.id IS NULL OR "
            "p.source_file IS DISTINCT FROM t._source_file OR "
            "p.imported_at IS DISTINCT FROM t._imported_at").format(qualified)).fetchone()[0]
        if mismatch:
            raise ValueError(f"{table}: {mismatch} correspondances incorrectes.")
        # Les UPDATE ne concernent que la nouvelle colonne ; les mesures ne sont pas reecrites logiquement.
        conn.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN _provenance_id SET NOT NULL, "
            "ADD CONSTRAINT {} FOREIGN KEY (_provenance_id) REFERENCES database_meta.provenance(id), "
            "DROP COLUMN _source_file, DROP COLUMN _imported_at").format(
                qualified,sql.Identifier(sql_name(table+"_provenance_fk"))))
        conn.execute(sql.SQL("CREATE INDEX {} ON {} (_provenance_id)").format(
            sql.Identifier(sql_name(table+"_provenance_id_idx")),qualified))
        after=groups(conn,read_relation(conn,schema,table))
        if before!=after:
            raise ValueError(f"{table}: groupes de provenance modifies, annulation.")
        return {"table":table,"status":"optimisee","rows":sum(r[2] for r in after),"provenances":len(after)}

def sizes(conn):
    rows=conn.execute("""SELECT n.nspname,c.relname,pg_table_size(c.oid),
        pg_indexes_size(c.oid),pg_total_relation_size(c.oid)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind='r' AND n.nspname IN ('donnees','database_meta')
        ORDER BY n.nspname,c.relname""").fetchall()
    return {"database_bytes":conn.execute("SELECT pg_database_size(current_database())").fetchone()[0],
            "tables":[dict(zip(["schema","table","data_bytes","index_bytes","total_bytes"],r)) for r in rows]}


COMPACT_SOURCE_TABLES = ("production_regionale", "charge_res2_6_9", "charge_res2_9_12")


def prepare_compact_sources(db, reference_schema):
    """Preparer les tables vides avant import ; ne jamais migrer une base peuplee."""
    aliases = {"timestamp with time zone": "timestamptz",
               "timestamp without time zone": "timestamp"}
    with db.connection.transaction():
        for table in COMPACT_SOURCE_TABLES:
            columns = {name: aliases.get(kind, kind)
                       for name, kind in reference_schema[table].items()
                       if name not in {"_source_file", "_imported_at", "_provenance_id"}}
            db.create_table(table, columns)
            if is_compact(db.connection, db.schema, table):
                continue
            populated = db.connection.execute(sql.SQL("SELECT 1 FROM {} LIMIT 1").format(
                sql.Identifier(db.schema, table))).fetchone()
            if populated:
                raise ValueError(f"{table}: table deja alimentee sans optimisation. "
                                 "Utiliser optimiser_provenance.py avec sauvegarde avant de reprendre.")
            optimize_table(db.connection, db.schema, table, apply=True)
