# Installer les outils et créer la base

**Ces fichiers sont préparés, mais aucune installation, création de base ou import n’a été lancé.** Les commandes ci-dessous sont à exécuter plus tard, quand tu voudras démarrer.

## 1. Ce qu’il faut installer

Pour ton environnement Ubuntu/WSL :

| Outil | À quoi il sert | Nécessaire ? |
| --- | --- | --- |
| PostgreSQL | Serveur qui stockera les tables | Oui |
| PostGIS | Extension pour les coordonnées et les traitements géographiques | Oui pour la base proposée |
| Client `psql` | Exécuter les fichiers SQL | Oui pour les commandes ci-dessous |
| Python et environnement `.venv` | Exécuter les scripts | Déjà utilisés dans le projet |
| `psycopg` | Permettre à Python de communiquer avec PostgreSQL | Oui pour l’import |
| DBeaver ou pgAdmin | Voir les tables avec une interface graphique | Facultatif |

Commandes d’installation système :

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib postgresql-client postgis
```

PostGIS doit être installé **pour la version du serveur PostgreSQL**. Si `CREATE EXTENSION postgis` indique que le fichier de contrôle manque, rechercher le paquet correspondant avec `apt search postgresql | grep postgis`, puis installer le paquet adapté, par exemple `postgresql-<version>-postgis-3`. Vérifier la version réellement installée avec `psql --version` et les informations du serveur ; elles peuvent différer si plusieurs versions coexistent.

Démarrer le serveur si nécessaire :

```bash
sudo service postgresql start
```

Depuis la racine de `Projet_Tuteuré`, installer le pilote Python :

```bash
.venv/bin/python -m pip install -r requirements-module-1.txt
```

Ce fichier ajoute uniquement les dépendances de l’import. Le fichier `requirements.txt` existant reste celui des autres traitements du projet.

## 2. Créer la base et son utilisateur — une seule fois

Toujours depuis la racine du projet :

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d postgres < sql/module_1/000_creation_base.sql
```

Le fichier crée :

- un utilisateur `enedis_app` ; `psql` demande son mot de passe pendant l’exécution ;
- une base `enedis`, appartenant à cet utilisateur ;
- l’extension PostGIS dans cette base.

Choisir un mot de passe et le garder en dehors des fichiers Git. Ce fichier initial n’est pas fait pour être rejoué si le rôle ou la base existent déjà. En cas d’erreur, vérifier les objets déjà créés ; ne pas supprimer une base existante pour relancer.

## 3. Configurer la connexion

Dans le terminal depuis lequel tu lanceras les prochaines commandes :

```bash
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=enedis
export PGUSER=enedis_app
read -rsp 'Mot de passe PostgreSQL : ' PGPASSWORD
export PGPASSWORD
printf '\n'
```

Le mot de passe saisi n’apparaît pas à l’écran et n’est pas écrit dans une commande conservée dans l’historique. Ces variables restent propres au terminal courant. Une configuration `.pgpass` est également possible, sans versionner ce fichier.

Dans DBeaver ou pgAdmin, renseigner ces mêmes hôte, port, base et utilisateur, ainsi que ton mot de passe.

## 4. Créer les tables et les vues

```bash
psql -X -v ON_ERROR_STOP=1 -f sql/module_1/001_structure_base.sql
psql -X -v ON_ERROR_STOP=1 -f sql/module_1/002_index_et_vues.sql
```

La structure couvre les familles de données prévues. Les tables des autres familles restent vides : seul l’import de consommation est fourni à ce stade.

Le fichier `001` utilise `CREATE TABLE IF NOT EXISTS` : le rejouer ne modifie pas une table existante pour l’aligner avec un SQL changé. Toute évolution devra avoir sa propre migration.

## 5. Importer le CSV de consommation

```bash
.venv/bin/python scripts/module_1/import_consommation.py
```

Le fichier attendu est `data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv`. Pour une autre copie de même structure :

```bash
.venv/bin/python scripts/module_1/import_consommation.py --source /chemin/vers/consommation.csv
```

L’import :

1. Calcule l’empreinte du fichier pour reconnaître un import identique.
2. Vérifie les colonnes avec `sql/module_1/colonnes_consommation.json`.
3. Conserve chaque ligne et les valeurs d’origine dans `staging.observation`.
4. Remplit `core.consommation_annuelle` avec les colonnes typées.
5. Convertit les cellules vides ou composées d’espaces en `NULL`, sans moyenne ni médiane.
6. Vérifie les comptages avant de valider la transaction.

Une valeur présente mais non convertible provoque un arrêt : elle n’est pas silencieusement remplacée par `NULL`. Une erreur annule les écritures de cet import. Le fichier brut reste intact. Le script lit en flux, mais sa transaction complète peut demander du temps, de l’espace disque et générer des journaux PostgreSQL importants : prévoir une marge au-delà de la taille du CSV.

Relancer le même fichier avec la même version du script n’ajoute aucune ligne. Une livraison différente crée un autre import ; **les vues ne choisissent pas automatiquement la livraison la plus récente**. Sélectionner un `id_import` pour éviter de mélanger des versions d’un même jeu.

Les codes géographiques sources sont importés, mais `id_territoire` reste vide tant qu’un référentiel historique fiable n’a pas été chargé. Cela ne bloque pas la conservation des données.

## 6. Vérifier après l’import

```bash
psql -X -v ON_ERROR_STOP=1 -f sql/module_1/003_verification_import.sql
```

Pour la livraison déjà analysée, on attend **3 763 258 lignes** et **446 907 consommations totales manquantes**. Ces valeurs sont des points de comparaison pour ce fichier, pas des constantes imposées aux futures livraisons.

Exemple de consultation détaillée :

```sql
SELECT id_import, code_commune, annee, code_categorie_consommation,
       conso_totale_mwh, consommation_manquante
FROM analytics.consommation_detail
WHERE id_import = 1
LIMIT 20;
```

Remplacer `1` par l’identifiant réellement indiqué par le script. Aucun total ni traitement prédictif n’est calculé par ces fichiers.

Après utilisation, on peut retirer le mot de passe du terminal :

```bash
unset PGPASSWORD
```

## 7. Ce qui reste à développer

- Les imports des Parquet de production et des CSV solaire, IRVE, réseau et courbes de charge.
- Le chargement des référentiels géographiques et les correspondances datées.
- Les règles métier d’agrégation et les éventuelles estimations propres aux modèles.
- Le suivi persistant des imports échoués : pour l’instant une erreur est affichée et la transaction annulée, sans ligne d’échec conservée en base.
- Les droits de lecture pour les autres membres, les sauvegardes et les vues destinées à l’application.

Le [schéma de la base](schema-base.md) explique les tables et leurs relations.
