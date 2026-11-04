"""Rangement des fichiers déjà livrés, sans dépendance au répertoire du script."""
from pathlib import Path

from .client import sql_name

CSV_TABLES = {
    "consommation/consommation-electrique-par-secteur-dactivite-commune.csv": "consommation_annuelle",
    "puissance_photovoltaique/puissance-solaire-installee-commune.csv": "solaire_commune",
    "puissance_photovoltaique/puissance-solaire-installee-epci.csv": "solaire_epci",
    "puissance_photovoltaique/puissance-solaire-installee-departement.csv": "solaire_departement",
    "puissance_photovoltaique/puissance-solaire-installee-region.csv": "solaire_region",
    "puissance_photovoltaique/description-des-champs.csv": "dictionnaire_solaire",
    "bornes_recharge/consolidation_transport_irve_statique.csv": "irve_statique",
    "bornes_recharge/consolidation_transport_irve_statique_rapport.csv": "irve_rapport",
    "reseau/poste-electrique.csv": "postes_electriques",
    "reseau/donnees-relatives-aux-lignes-et-aux-postes.csv": "statistiques_reseau",
    "courbes_de_charge/RES2-6-9.csv": "charge_res2_6_9",
    "courbes_de_charge/RES2-9-12.csv": "charge_res2_9_12",
}


def import_existing_data(db, raw_directory, force=False, csv_types=None):
    """Importer tous les CSV, Parquet et documents JSON/TXT sous raw_directory.

    Les CSV restent en texte par défaut pour conserver toutes les valeurs.
    csv_types peut être {nom_table: {nom_colonne_sql: type_sql}}.
    Chaque fichier est une transaction ; un échec n'annule pas les fichiers
    précédents. Relancer après correction reprend sans recharger les inchangés.
    """
    root = Path(raw_directory).resolve()
    if not root.is_dir():
        raise ValueError(f"Dossier de données absent : {root}")
    files = sorted(p for p in root.rglob("*") if p.is_file()
                   and p.suffix.lower() in {".csv", ".parquet", ".json", ".txt"}
                   and not p.name.endswith(":Zone.Identifier"))
    if not files:
        raise ValueError("Aucun fichier CSV, Parquet, JSON ou TXT trouvé.")
    for path in files:
        relative = path.relative_to(root).as_posix()
        print(f"Import : {relative}", flush=True)
        suffix = path.suffix.lower()
        try:
            if suffix == ".csv":
                table = CSV_TABLES.get(relative)
                if relative.startswith("bornes_recharge/consolidation-nationale-irve-dynamique-"):
                    table = "irve_dynamique"
                if table is None:
                    # Les sources nouvelles peuvent aussi être importées explicitement
                    # avec db.import_csv(path, table='nom_choisi').
                    table = sql_name(relative.removesuffix(path.suffix))
                result = db.import_csv(path, table, types=(csv_types or {}).get(table), force=force)
            elif suffix == ".parquet":
                if relative.startswith("production_regionale/"):
                    table, base = "production_regionale", root / "production_regionale"
                else:
                    # Le nom est explicite pour éviter de fusionner des jeux inconnus.
                    table, base = sql_name(relative.removesuffix(path.suffix)), path.parent
                result = db.import_parquet(path, table, dataset_root=base, force=force)
            elif suffix == ".json":
                result = db.import_json_document(path, force=force)
            else:
                result = db.import_text_document(path, force=force)
        except Exception as error:
            raise RuntimeError(f"Import interrompu sur {relative} ; ce fichier est annulé. "
                               "Les fichiers validés précédemment restent disponibles.") from error
        yield result
