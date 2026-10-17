# Production régionale en Parquet

## Conversion depuis API ENEDIS

Depuis la racine du projet, avec les dépendances de `requirements.txt` installées :

```bash
.venv/bin/python scripts/convert_production_regionale_parquet.py
```

Le script exige un téléchargement terminé et une liste de pages conforme au checkpoint. Il lit les pages JSON compressées par lots de 100, sans charger tout le jeu en mémoire. Les sources restent dans `data/raw/production_regionale/`.

Le dataset est écrit dans `data/processed/production_regionale/`, avec des dossiers Hive `year=2023/`, etc., et des fichiers de 500 000 lignes maximum, compressés avec Zstandard. Les années présentes sont déterminées par les données, sans liste prédéfinie.

Les nombres et identifiants conservent un schéma stable même lorsque des valeurs sont absentes. Les codes géographiques et indices de représentativité (dont `S`) restent des chaînes. `horodate` devient un timestamp UTC ; `horodate_source` conserve la valeur source avec son décalage horaire. La partition `year` est calculée en heure française (`Europe/Paris`) : le début du 1er janvier n’est donc pas classé dans l’année précédente à cause de la conversion UTC.

## Validation et interruption

Le script vérifie la chaîne de pagination, les identifiants à l’intérieur de chaque page, le schéma de tous les fichiers Parquet, les comptages par année et la cohérence entre timestamps et partitions. Il relit les timestamps Parquet pour contrôler le classement annuel. Le contrôle global des doublons entre pages reste à effectuer.

Le dataset n’est publié qu’après validation, par renommage du dossier temporaire `production_regionale.building`. Un échec laisse ce dossier séparé pour diagnostic ; il n’existe pas de reprise de conversion. Pour relancer après un échec, choisir une autre destination vide via `--output`, ou retirer explicitement le dossier temporaire après vérification. Une destination existante n’est jamais écrasée.

Le rapport `_conversion.json` contient les comptages, les bornes temporelles et la taille des fichiers. La source est verrouillée pendant la conversion pour empêcher une exécution concurrente du téléchargeur.

## Lecture

```python
import pyarrow.dataset as ds

production = ds.dataset(
    "data/processed/production_regionale",
    format="parquet",
    partitioning="hive",
)

# Lire uniquement une année et les colonnes utiles.
solar = production.to_table(
    columns=["horodate", "code_region", "total_energie_injectee_wh"],
    filter=(ds.field("year") == 2025)
        & (ds.field("filiere_de_production") == "F5 : Solaire")
        & (ds.field("plage_de_puissance_injection") == "P0 : Total toutes puissances"),
)

# Pour parcourir toutes les données sans chargement global en RAM :
for batch in production.scanner(batch_size=64_000).to_batches():
    pass  # Traiter chaque lot.
```

Éviter de sommer les catégories détaillées avec les catégories `P0` ou `F0`, qui représentent déjà des totaux. Les énergies sont en Wh ; le stockage Parquet ne change pas l’unité ni les règles métier.
