**Mise a jour types :** les CSV connus sont desormais types automatiquement. Pour une base deja importee, suivre [la migration](migration-types.md) avant tout nouvel import. Cette consigne remplace les mentions de CSV tous en texte ci-dessous.

Parcours de reference : [initialisation et evolution Python](parcours-python.md).

# Utiliser la base commune depuis Python

## Ce qui change

Le code réutilisable est maintenant dans **`src/enedis/database/`**, à côté de `prediction/` et `scenarios/`. Les membres du groupe appellent des fonctions Python ; ces fonctions exécutent le SQL nécessaire.

La base est créée dans WSL, les données sont importées et la migration des types a été appliquée. Les types et comptages ont été contrôlés ; la suite complète de tests d'intégration reste à développer.

Cette interface est le point d’entrée commun pour centraliser les fichiers et faire évoluer les tables depuis Python.

## 1. Installer le package et se connecter
A voir plus tards

Installer PostgreSQL et les outils selon [les consignes d'installation](consignes-installation-database.md). PostGIS reste utile pour les futurs traitements spatiaux ; cet import générique n’en dépend pas et ne construit pas de géométries automatiquement.

Depuis la racine du dépôt :

```bash
.venv/bin/python -m pip install -e '.[database]'
```

L’installation permet ensuite d’utiliser `from enedis.database import ...` dans les scripts et notebooks de cet environnement, quel que soit leur dossier courant. Chaque collègue doit installer le package dans son propre environnement.

Configurer `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` et le mot de passe via `.pgpass` ou `PGPASSWORD`. **Pour partager la même base, tous les membres du groupe doivent pointer vers le même serveur PostgreSQL**, pas chacun vers son propre `localhost`. Le serveur doit être accessible et les comptes doivent avoir les droits appropriés. Le package ne configure pas le réseau ni les comptes.

Si la base n’existe pas, un compte ayant le droit `CREATEDB` peut la créer en Python :

```python
from enedis.database import create_database

create_database("enedis", admin_dsn="dbname=postgres")
```

Cette fonction crée la base si elle est absente, sans la supprimer si elle existe. Elle ne crée pas d’utilisateur et n’installe pas le serveur. La connexion administrative utilise les paramètres PG* pour les valeurs non précisées. Ensuite, utiliser `PGDATABASE=enedis` avec le compte autorisé pour les imports.

## 2. Importer tous les fichiers actuels

```python
from enedis.database import Database, import_existing_data

with Database() as db:
    for result in import_existing_data(db, "/chemin/vers/Projet_Tuteuré/data/raw"):
        print(result)
```

Ou depuis la racine du dépôt :

```bash
.venv/bin/python scripts/module_1/preparer_base.py --import-all
```

Les fichiers sont lus en flux ou par lots. Chaque fichier est validé dans sa propre transaction. Si un import échoue, ses écritures sont annulées ; les fichiers précédents restent chargés. Une relance ignore les fichiers inchangés grâce à leur empreinte et au suivi d’import.

Si un fichier du même chemin a changé, ses anciennes lignes sont remplacées **dans une transaction**, sans remplacer les autres fichiers de la table. Le chemin source identifie la livraison : déplacer le dossier ou ajouter une copie d’un fichier sous un autre chemin peut créer une autre livraison, même si les données sont identiques. Utiliser un emplacement d’import stable et éviter les copies en double.

La base est persistante : les membres du groupe n’ont pas à l’importer à chaque analyse. Une fois remplie, ils utilisent uniquement les fonctions de lecture.

## 3. Où vont les fichiers ?

Le schéma `donnees` contient les tables importées. Le schéma `database_meta` conserve leur provenance et le dictionnaire de noms des colonnes.

| Source dans `data/raw/` | Table dans `donnees` |
| --- | --- |
| CSV de consommation | `consommation_annuelle` |
| Solaire commune / EPCI / département / région | `solaire_commune`, `solaire_epci`, `solaire_departement`, `solaire_region` |
| Description des champs solaires | `dictionnaire_solaire` |
| Les 70 Parquet de production | `production_regionale`, avec les partitions `year` conservées |
| IRVE statique / dynamique / rapport | `irve_statique`, `irve_dynamique`, `irve_rapport` |
| Postes électriques | `postes_electriques` |
| Statistiques de lignes et postes | `statistiques_reseau` |
| Les deux CSV RES2 | `charge_res2_6_9` et `charge_res2_9_12` |
| Documents JSON / TXT | `documents_source` et `documents_texte` |

Les nouveaux CSV/Parquet sont également reconnus, avec un nom de table dérivé du chemin. Pour choisir précisément un nom et regrouper plusieurs fichiers, préférer les appels explicites ci-dessous. Les fichiers Windows `:Zone.Identifier` sont ignorés.

Les noms des colonnes deviennent des noms SQL sans accents ni espaces. Les correspondances originales sont conservées dans `database_meta.fichier`. Chaque table reçoit `_source_file` et `_imported_at` pour retrouver la provenance. Ces deux noms sont réservés.

### Types et valeurs manquantes

- **CSV : texte par défaut**, pour centraliser toutes les valeurs sans inventer des types ni perdre des marqueurs. Les cellules vides ou composées d’espaces deviennent `NULL`. Les autres chaînes restent inchangées, y compris `N/A`.
- **Parquet : types issus du schéma**, avec conservation des valeurs nulles et des dates. Un type non pris en charge provoque une erreur explicite.
- Aucune moyenne, médiane, somme ou estimation n’est calculée.

On peut définir des types à la première création d’une table CSV :

```python
with Database() as db:
    db.import_csv(
        "/chemin/consommation.csv",
        table="consommation_annuelle",
        types={"annee": "integer", "nb_sites": "bigint", "conso_totale_mwh": "numeric"},
        delimiter=",",
    )
```

Pour appliquer ces types lors de l’import global, fournir `csv_types={"consommation_annuelle": {...}}` à `import_existing_data`. Garder cette configuration pour les relances. Une valeur incompatible arrête l’import au lieu d’être perdue silencieusement. Si la table existe déjà en texte, le package refuse de changer son type automatiquement : une migration contrôlée sera nécessaire.

## 4. Lire les données dans un script de prédiction ou scénario

```python
from enedis.database import Database

with Database() as db:
    consommation = db.read_table(
        "consommation_annuelle",
        columns=["code_commune", "annee", "conso_totale_mwh"],
        filters={"annee": "2024"},  # entier 2024 si la colonne a été créée en integer
        limit=10_000,
    )

# consommation est un DataFrame pandas utilisable après fermeture de la connexion.
```

La lecture est limitée à 1 000 lignes par défaut. Choisir une limite appropriée ; `limit=None` charge explicitement toute la sélection en mémoire. Aucun ordre des lignes n’est garanti : trier les séries avant les prévisions. Les colonnes CSV en texte peuvent être converties dans le DataFrame ou être typées dès la création comme indiqué plus haut.

## 5. Ajouter une table et des colonnes sans écrire du SQL

```python
with Database() as db:
    db.create_table("meteo", {
        "code_commune": "text",
        "date_mesure": "date",
        "temperature": "numeric",
    })
```

Le lendemain, ajouter un champ dans le dictionnaire et relancer :

```python
with Database() as db:
    db.create_table("meteo", {
        "code_commune": "text",
        "date_mesure": "date",
        "temperature": "numeric",
        "ensoleillement": "numeric",
    })
```

La table existante est conservée et la nouvelle colonne est ajoutée. Elle vaut `NULL` pour les anciennes lignes, tant qu’on ne dispose pas de valeurs pour les compléter.

On peut aussi écrire simplement :

```python
with Database() as db:
    db.add_columns("meteo", {"humidite": "numeric"})
```

**On change la description des colonnes, pas seulement leur nombre.** Python doit connaître leur nom et leur type. Retirer une colonne du dictionnaire ne la supprime pas de la base. Les renommages, suppressions et conversions de types ne sont volontairement pas automatiques : ils peuvent perdre ou modifier des données.

## 6. Ajouter une nouvelle source

```python
with Database() as db:
    db.import_csv("/chemin/nouvelle_source.csv", table="nouvelle_source", delimiter=";")
    db.import_parquet("/chemin/mesures.parquet", table="mesures")
```

Une colonne supplémentaire dans un fichier source est ajoutée automatiquement lors de l’import. Les lignes des autres fichiers déjà présents dans la même table gardent `NULL` pour cette colonne. Un nom qui se normalise comme une autre colonne provoque une erreur plutôt qu’une fusion silencieuse.

Un changement de type est refusé. Pour recharger explicitement un fichier inchangé, utiliser `force=True` : ses lignes sont remplacées, pas ajoutées en double.

## 7. Limites de cette première interface

- Les règles géographiques, unités et correspondances entre sources restent à définir : centraliser les fichiers ne les rend pas automatiquement comparables.
- Les colonnes personnalisées ajoutées dans une table importée ne sont pas sauvegardées si les lignes de leur fichier source sont remplacées. Conserver les résultats de modèles et enrichissements durables dans des tables séparées.
- La lecture proposée renvoie un DataFrame, pas encore un lecteur de résultats par lots.
- Les contrôles de formats et doublons existants restent utiles avant les imports typés.
- Le package ne choisit pas automatiquement la livraison courante lorsque plusieurs chemins décrivent le même jeu.
- Les utilisateurs qui créent/importent ont besoin de droits d’écriture ; un compte de lecture peut utiliser `read_table` sans lancer les fonctions de création.
- Les contraintes métier, index spécialisés et migrations complexes pourront être ajoutés dans le package sans demander aux collègues de rédiger le SQL.

## Vérification avant usage collectif

Des tests sans serveur sont fournis dans `tests/test_database_files.py` (noms de colonnes, CSV, valeurs vides et catalogue). Ils n’ont pas été exécutés lors de cette préparation. Il reste à valider sur une base de développement : création, ajout de colonne, relance sans doublon, annulation d’un import invalide, remplacement d’un fichier modifié et import Parquet avec partitions. Ne pas considérer ces comportements comme validés sur PostgreSQL avant cet essai.
