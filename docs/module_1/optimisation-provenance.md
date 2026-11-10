# Optimisation de la provenance des imports

## Objectif

Les chemins des fichiers et les dates d’import sont répétés sur chaque ligne. Le script les regroupe dans `database_meta.provenance` et conserve une clé `_provenance_id` de type `bigint`, obligatoire, indexée et munie d’une clé étrangère dans chaque table optimisée. Chaque couple fichier/date est conservé. Les valeurs métier, leurs types, les zéros et les valeurs NULL restent identiques.

Par défaut, seules `production_regionale`, `charge_res2_6_9` et `charge_res2_9_12` sont concernées. La taille finale dépend du stockage PostgreSQL ; aucun gain précis n’est garanti.

## Préparation

Exécuter depuis la racine du projet dans WSL avec l’environnement Python installé :

```bash
source .venv/bin/activate
pg_dump --version
pg_restore --version
df -h . ~
```

Les outils PostgreSQL doivent être compatibles avec la version du serveur. Prévoir de l’espace pour la sauvegarde, les nouvelles versions des lignes, les journaux WAL et une copie temporaire de la plus grosse table lors du VACUUM. Le volume de la base seul ne suffit pas pour dimensionner cet espace. Arrêter les imports et les traitements qui utilisent ces tables pendant l’opération : la migration et VACUUM FULL bloquent leur accès.

## 1. Contrôle sans modification de la base

```bash
python scripts/module_1/optimiser_provenance.py
```

Le mot de passe demandé est celui du rôle PostgreSQL `enedis_owner`. Les effectifs par fichier sont comparés à `database_meta.fichier`. Une provenance absente ou un comptage incohérent bloque la migration. Le contrôle peut prendre du temps sur plusieurs dizaines de millions de lignes.

## 2. Sauvegarde et optimisation

Choisir un nouveau nom de sauvegarde à chaque exécution : un fichier existant est refusé.

```bash
python scripts/module_1/optimiser_provenance.py --apply --backup "$HOME/sauvegardes/enedis-avant-optimisation.dump" --vacuum-full
```

Le script effectue une sauvegarde complète au format PostgreSQL custom, vérifie que son catalogue est lisible, puis optimise les tables une par une dans des transactions. Cette vérification de l’archive ne remplace pas un essai de restauration. Une erreur pendant la migration d’une table annule cette migration ; les tables terminées précédemment restent optimisées.

`VACUUM FULL` réécrit ensuite chaque table pour rendre l’espace libéré au système. Sans cette option, la taille peut temporairement augmenter. En cas d’échec du VACUUM, la migration déjà validée reste en place. Une nouvelle exécution, avec un nouveau chemin de sauvegarde, reconnaît les tables déjà optimisées et permet de reprendre le VACUUM.

Pour procéder table par table, ajouter par exemple `--table production_regionale`. L’option est répétable. Laisser le terminal ouvert jusqu’à la fin.

## 3. Vérification finale

Le script affiche les tailles avant/après et leur différence en Gio. Le détail par table, données et index, est enregistré dans `data/processed/optimisation/bilan-*.json`. La mesure concerne la base PostgreSQL, pas la sauvegarde, les fichiers sources ni la taille du disque virtuel WSL.

Relancer le contrôle sans `--apply`, puis l’audit des imports si nécessaire. Dans psql, la taille peut aussi être consultée directement :

```sql
SELECT current_database(), pg_size_pretty(pg_database_size(current_database()));
```

## Interface Python et schéma physique

`Database.read_table()` restitue toujours `_source_file` et `_imported_at` en reconstruisant leur valeur par jointure. Les imports suivants et l’audit prennent en charge les deux formats. Les ajouts de colonnes métier restent possibles.

Dans psql, les tables optimisées contiennent physiquement `_provenance_id` à la place des deux anciennes colonnes. Les requêtes SQL directes utilisant ces anciennes colonnes doivent effectuer une jointure :

```sql
SELECT t.*, p.source_file AS _source_file, p.imported_at AS _imported_at
FROM donnees.production_regionale AS t
JOIN database_meta.provenance AS p ON p.id = t._provenance_id
LIMIT 10;
```

Une vue dépendant des anciennes colonnes empêche leur suppression : la transaction échoue sans suppression en cascade. La nouvelle table de provenance conserve également les références historiques après un remplacement d’import.

## Validation du code

Le test `tests/integration_optimisation.py` utilise un cluster PostgreSQL temporaire isolé : égalité des valeurs avant/après, dates distinctes, contrôle sans mutation, réimport, ajout de colonne, annulation d’un import invalide, refus de provenance absente et VACUUM. Il ne se connecte pas à la base `enedis`.
