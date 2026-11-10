"""Controle par defaut ; sauvegarde obligatoire avant migration explicite."""
import argparse
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime
import psycopg
from psycopg import sql
from enedis.database.optimization import optimize_table, sizes
from enedis.database.catalogue import SOURCE_INDEXES
from enedis.database.client import identifier

ROOT=Path(__file__).resolve().parents[2]

def backup_database(path,params):
    if path.exists():
        raise ValueError("Le fichier de sauvegarde existe deja ; choisir un nouveau nom.")
    for command in ("pg_dump","pg_restore"):
        if shutil.which(command) is None:
            raise ValueError(f"{command} doit etre disponible dans PATH.")
    path.parent.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    env.update({"PGHOST":params["host"],"PGPORT":str(params["port"]),
                "PGUSER":params["user"],"PGDATABASE":"enedis"})
    if params.get("password"): env["PGPASSWORD"]=params["password"]
    result=subprocess.run(["pg_dump","-w","-Fc","-f",str(path)],env=env,capture_output=True)
    if result.returncode:
        raise RuntimeError("Echec pg_dump ; aucune migration lancee. Verifier version, droits et espace.")
    result=subprocess.run(["pg_restore","--list",str(path)],capture_output=True)
    if result.returncode or path.stat().st_size==0:
        raise RuntimeError("Archive de sauvegarde illisible ; aucune migration lancee.")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user",default=os.environ.get("PGUSER","enedis_owner"))
    parser.add_argument("--host",default=os.environ.get("PGHOST","127.0.0.1"))
    parser.add_argument("--port",type=int,default=int(os.environ.get("PGPORT","5432")))
    parser.add_argument("--table",action="append",help="Table cible ; repetable. Par defaut les trois grosses tables.")
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--backup",type=Path)
    parser.add_argument("--vacuum-full",action="store_true",help="Reecrire les tables apres migration pour recuperer l'espace")
    args=parser.parse_args()
    if args.apply and not args.backup: parser.error("--backup obligatoire avec --apply")
    if args.vacuum_full and not args.apply: parser.error("--vacuum-full exige --apply")
    tables=args.table or ["production_regionale","charge_res2_6_9","charge_res2_9_12"]
    for table in tables:
        identifier(table)
        if table not in SOURCE_INDEXES: parser.error("Table source non prise en charge : "+table)
    password=os.environ.get("PGPASSWORD")
    if password is None: password=getpass.getpass("Mot de passe PostgreSQL : ")
    params=dict(host=args.host,port=args.port,user=args.user,dbname="enedis",connect_timeout=10)
    if password: params["password"]=password
    output=ROOT/"data/processed/optimisation"
    output.mkdir(parents=True,exist_ok=True)
    report_path=output/("bilan-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".json")
    report={"apply":args.apply,"tables":[]}
    with psycopg.connect(**params,autocommit=True) as conn:
        if not args.apply:
            conn.execute("SET default_transaction_read_only=on")
        report["before"]=sizes(conn)
        for table in tables:
            print(optimize_table(conn,"donnees",table,apply=False),flush=True)
        if args.apply:
            print("Sauvegarde complete en cours...",flush=True)
            backup_database(args.backup.expanduser(),params)
            report["backup"]=str(args.backup.expanduser())
        try:
            for table in tables:
                result=optimize_table(conn,"donnees",table,apply=args.apply)
                report["tables"].append(result)
                print(result,flush=True)
                report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
                if args.vacuum_full:
                    print("Reecriture et analyse : "+table,flush=True)
                    conn.execute("SET lock_timeout='5s'")
                    conn.execute(sql.SQL("VACUUM (FULL, ANALYZE) {}").format(sql.Identifier("donnees",table)))
                    optimize_table(conn,"donnees",table,apply=False)
        finally:
            report["after"]=sizes(conn)
            report["saved_bytes"]=report["before"]["database_bytes"]-report["after"]["database_bytes"]
            report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(f"Taille avant : {report['before']['database_bytes']/2**30:.2f} Gio")
        print(f"Taille apres : {report['after']['database_bytes']/2**30:.2f} Gio")
        print(f"Difference : {report['saved_bytes']/2**30:.2f} Gio")
        print("Rapport : "+str(report_path))

if __name__=="__main__":
    main()
