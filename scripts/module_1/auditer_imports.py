"""Audit en lecture seule : sources, provenance, comptages et espace disque."""
import argparse
import csv
import getpass
import hashlib
import json
import os
from pathlib import Path
import psycopg
from psycopg import sql
from enedis.database.catalogue import CSV_TABLES
from enedis.database.client import sql_name
from enedis.database.provenance import read_relation

ROOT = Path(__file__).resolve().parents[2]

def source_info(path, root):
    relative = path.relative_to(root).as_posix()
    suffix = path.suffix.lower()
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            digest.update(block)
    if suffix == ".csv":
        table = CSV_TABLES.get(relative, sql_name(relative.removesuffix(path.suffix)))
        if relative.startswith("bornes_recharge/consolidation-nationale-irve-dynamique-"):
            table = "irve_dynamique"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(65536)
            stream.seek(0)
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
            reader = csv.reader(stream, delimiter=delimiter)
            header = next(reader, None)
            if not header:
                raise ValueError(f"CSV sans en-tete : {relative}")
            count = 0
            for row in reader:
                if len(row) != len(header):
                    raise ValueError(f"CSV mal forme : {relative}, enregistrement {count+2}")
                count += 1
    elif suffix == ".parquet":
        import pyarrow.parquet as pq
        count = pq.ParquetFile(path).metadata.num_rows
        table = "production_regionale" if relative.startswith("production_regionale/") else sql_name(relative.removesuffix(path.suffix))
    else:
        count = 1
        table = "documents_source" if suffix == ".json" else "documents_texte"
        if suffix == ".json":
            json.loads(path.read_text(encoding="utf-8-sig"))
    after = path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError(f"Fichier modifie pendant l'audit : {relative}")
    return table, str(path), count, digest.hexdigest()

def write_csv(path, fields, rows):
    with path.open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,default=ROOT/"data/raw")
    parser.add_argument("--output",type=Path,default=ROOT/"data/processed/audit_imports")
    parser.add_argument("--host",default=os.environ.get("PGHOST","127.0.0.1"))
    parser.add_argument("--port",type=int,default=int(os.environ.get("PGPORT","5432")))
    parser.add_argument("--user",default=os.environ.get("PGUSER","enedis_owner"))
    parser.add_argument("--sources-only",action="store_true")
    args=parser.parse_args()
    root=args.raw.resolve()
    if not root.is_dir(): raise ValueError("Dossier raw absent")
    sources={}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".csv",".parquet",".json",".txt"} and not path.name.endswith(":Zone.Identifier"):
            table,name,count,sha=source_info(path,root)
            sources[table,name]=(count,sha)
            print(f"{path.relative_to(root)} : {count} lignes",flush=True)
    if not sources: raise ValueError("Aucune source")
    args.output.mkdir(parents=True,exist_ok=True)
    write_csv(args.output/"sources.csv",["table","fichier","lignes","sha256"],
              [(t,n,c,h) for (t,n),(c,h) in sources.items()])
    if args.sources_only: return
    password=os.environ.get("PGPASSWORD")
    if password is None: password=getpass.getpass("Mot de passe PostgreSQL : ")
    params=dict(host=args.host,port=args.port,user=args.user,dbname="enedis",connect_timeout=10)
    if password: params["password"]=password
    with psycopg.connect(**params) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        meta={(t,n):(count,sha) for t,n,count,sha in conn.execute(
            "SELECT table_name,source_file,rows_count,sha256 FROM database_meta.fichier WHERE schema_name='donnees'")}
        tables=[r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='donnees'")]
        actual={}
        for table in tables:
            has_source=conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='donnees' AND table_name=%s AND column_name IN ('_source_file','_provenance_id')",(table,)).fetchone()
            if not has_source: continue
            print(f"Comptage en base : {table}",flush=True)
            for name,count in conn.execute(sql.SQL("SELECT _source_file,count(*) FROM {} GROUP BY _source_file").format(read_relation(conn,"donnees",table))):
                actual[table,name]=count
        report=[]
        for key in sorted(set(sources)|set(meta)|set(actual),key=lambda x:(x[0],x[1] or "")):
            source=sources.get(key)
            tracking=meta.get(key)
            count=actual.get(key,0)
            problems=[]
            if source is None: problems.append("source_locale_absente_ou_chemin_different")
            if tracking is None: problems.append("suivi_absent")
            if source and count!=source[0]: problems.append("ecart_base_source")
            if tracking and count!=tracking[0]: problems.append("ecart_base_suivi")
            if source and tracking and source[1]!=tracking[1]: problems.append("empreinte_differente")
            report.append((*key,source[0] if source else None,tracking[0] if tracking else None,count,
                           ";".join(problems) or "OK"))
        write_csv(args.output/"comparaison.csv",["table","fichier","lignes_source","lignes_suivi","lignes_base","statut"],report)
        groups={}
        for (table,name),(count,sha) in meta.items():
            groups.setdefault((table,sha),[]).append(name)
        write_csv(args.output/"fichiers_identiques.csv",["table","sha256","nombre_chemins","chemins"],
                  [(t,h,len(names)," | ".join(names)) for (t,h),names in groups.items() if len(names)>1])
        sizes=conn.execute("""SELECT n.nspname,c.relname,
            pg_relation_size(c.oid),pg_table_size(c.oid),pg_indexes_size(c.oid),pg_total_relation_size(c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
            AND n.nspname NOT LIKE 'pg_toast%'
            ORDER BY pg_total_relation_size(c.oid) DESC""").fetchall()
        write_csv(args.output/"tailles.csv",["schema","table","table_principale_octets","table_avec_toast_octets","index_octets","total_octets"],sizes)
        size=conn.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
        anomalies=sum(row[-1]!="OK" for row in report)
        print(f"Base : {size}. Comparaisons : {len(report)}, anomalies : {anomalies}.")
        print(f"Rapports : {args.output}")
        if anomalies: raise SystemExit(2)

if __name__=="__main__":
    main()
