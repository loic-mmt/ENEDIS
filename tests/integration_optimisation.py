"""Test explicite sur un cluster temporaire isole ; ne contacte jamais enedis."""
from pathlib import Path
import tempfile
import subprocess
import os
import psycopg
from enedis.database import Database
from enedis.database.optimization import optimize_table
from enedis.database.provenance import is_compact
from psycopg import sql

def main():
    bindir=Path(subprocess.check_output(["pg_config","--bindir"],text=True).strip())
    with tempfile.TemporaryDirectory(prefix="enedis-opt-test-") as tmp:
        root=Path(tmp)
        data=root/"cluster"
        sock=root/"socket"
        sock.mkdir()
        subprocess.run([str(bindir/"initdb"),"-D",str(data),"-A","trust","--no-locale","-E","UTF8"],check=True,stdout=subprocess.DEVNULL)
        subprocess.run([str(bindir/"pg_ctl"),"-D",str(data),"-l",str(root/"server.log"),"-o",f"-k {sock} -h '' -p 55439","-w","start"],check=True,stdout=subprocess.DEVNULL)
        try:
            dsn=f"host={sock} port=55439 dbname=postgres"
            with Database(dsn) as db:
                from enedis.database.optimization import prepare_compact_sources, COMPACT_SOURCE_TABLES
                schema = {table: {"code": "text", "mesure": "numeric",
                          "_source_file": "text", "_imported_at": "timestamp with time zone"}
                          for table in COMPACT_SOURCE_TABLES}
                prepare_compact_sources(db, schema)
                for table in COMPACT_SOURCE_TABLES:
                    assert is_compact(db.connection, "donnees", table)
                fresh = root / "fresh.csv"
                fresh.write_text("code;mesure\n001;0\n002;\n003;12.345\n")
                result = db.import_csv(fresh, "production_regionale", types={"mesure": "numeric"}, delimiter=";")
                assert result["rows"] == 3
                prepare_compact_sources(db, schema)
                assert db.import_csv(fresh, "production_regionale", types={"mesure": "numeric"}, delimiter=";")["status"] == "deja_importe"
                frame = db.read_table("production_regionale")
                assert len(frame) == 3 and frame.mesure.isna().sum() == 1
                assert str(frame.loc[frame.code == "003", "mesure"].iloc[0]) == "12.345"
                assert frame.loc[frame.code == "001", "mesure"].iloc[0] == 0
                source=root/"source.csv"
                source.write_text("code;mesure\n01001;0\n2A004;\n01002;12.345\n")
                options=dict(table="test_data",types={"mesure":"numeric"},delimiter=";")
                db.import_csv(source,**options)
                before=db.read_table("test_data",limit=None).sort_values("code").reset_index(drop=True)
                # Plusieurs dates pour le meme fichier doivent etre conservees.
                db.connection.execute("UPDATE donnees.test_data SET _imported_at=_imported_at-interval '1 day' WHERE code='01001'")
                before=db.read_table("test_data",limit=None).sort_values("code").reset_index(drop=True)
                assert optimize_table(db.connection,"donnees","test_data")["status"]=="controle_valide"
                assert not is_compact(db.connection,"donnees","test_data")
                optimize_table(db.connection,"donnees","test_data",True)
                after=db.read_table("test_data",limit=None).sort_values("code").reset_index(drop=True)
                import pandas as pd
                pd.testing.assert_frame_equal(before,after)
                assert db.import_csv(source,**options)["status"]=="deja_importe"
                db.add_columns("test_data",{"annotation":"text"})
                assert len(db.read_table("test_data",filters={"_source_file":str(source)}))==3
                source.write_text("code;mesure\n01001;1.234\n2A004;0\n")
                assert db.import_csv(source,**options)["rows"]==2
                assert len(db.read_table("test_data",limit=None))==2
                assert optimize_table(db.connection,"donnees","test_data",True)["status"]=="deja_optimisee"
                source.write_text("code;mesure\n01001;invalid\n")
                try: db.import_csv(source,**options)
                except psycopg.Error: pass
                else: raise AssertionError("Import invalide accepte")
                assert len(db.read_table("test_data",limit=None))==2
                source.write_text("code;mesure\n01001;5\n")
                db.import_csv(source,"bad_data",types={"mesure":"numeric"},delimiter=";")
                db.connection.execute("UPDATE donnees.bad_data SET _source_file=NULL")
                try: optimize_table(db.connection,"donnees","bad_data",True)
                except ValueError: pass
                else: raise AssertionError("Provenance invalide acceptee")
                assert not is_compact(db.connection,"donnees","bad_data")
                db.connection.execute("VACUUM (FULL, ANALYZE) donnees.test_data")
                assert len(db.read_table("test_data"))==2
                print("OK : conservation exacte, dates distinctes, controle sans mutation, relance, remplacement, rollback, ajout de colonne et VACUUM.")
        finally:
            subprocess.run([str(bindir/"pg_ctl"),"-D",str(data),"-m","fast","-w","stop"],check=True,stdout=subprocess.DEVNULL)

if __name__=="__main__": main()
