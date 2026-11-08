# Audit de correspondance entre fichiers et base

Une taille PostgreSQL de 17 Go ne prouve pas une duplication. Les Parquet sont
compressés ; PostgreSQL ajoute des en-têtes de lignes, des index et des colonnes
de provenance répétées. La répartition réelle doit être mesurée.

## Exécution

Depuis la racine avec le Python du projet :

    python scripts/module_1/auditer_imports.py --user enedis_owner

Adapter --user au propriétaire local. Sur Windows, utiliser
.\.venv\Scripts\python.exe à la place de python. Le mot de passe est demandé.
--raw permet d'indiquer le dossier des sources ; --sources-only recompte seulement
les fichiers et n'ouvre aucune connexion. Les contrôles peuvent prendre plusieurs minutes.
Éviter de modifier les sources ou de lancer un import pendant cet audit.
La connexion PostgreSQL est explicitement en lecture seule, avec un instantané
cohérent pour les comptages. Aucune suppression ou correction automatique.

## Rapports dans data/processed/audit_imports

- sources.csv : comptage réel des enregistrements CSV (pas des lignes physiques),
  lignes déclarées dans les métadonnées Parquet et empreinte SHA-256 de chaque fichier.
  Un document JSON/TXT correspond à une ligne, comme lors de l'import.
- comparaison.csv : rapprochement fichier/source, suivi database_meta et comptage
  réel des lignes par _source_file. OK signifie des nombres égaux et la même empreinte.
- fichiers_identiques.csv : même empreinte importée dans la même table depuis plusieurs
  chemins. Ce sont des copies potentielles à examiner, pas des suppressions à effectuer.
- tailles.csv : taille de chaque table et de ses index, pour tous les schémas applicatifs.
  table_avec_toast_octets inclut le stockage auxiliaire ; ne pas l'additionner à
  table_principale_octets. total_octets inclut déjà les index.

Un chemin local différent de celui de l'import est signalé ; il ne prouve pas
une erreur de contenu. Un code de sortie 2 indique des anomalies de correspondance.
Les tables de résultats sans _source_file ne sont pas comparées aux fichiers,
mais leur espace figure dans tailles.csv.

## Interprétation

Si chaque fichier possède autant de lignes en base que dans sa source, sans
autre provenance et avec une empreinte identique, il n'y a pas de multiplication
des lignes visible par ce contrôle. Cela ne prouve pas l'égalité de chaque valeur :
une modification manuelle compensée ou des doublons déjà présents dans les
sources nécessitent une comparaison de contenu ou des contrôles de clés métier.

La clé métier dépend du jeu : commune/année seule n'est pas suffisante pour la
consommation ; région/horodatage seul ne suffit pas pour la production.
Les secteurs, catégories, filières et plages de puissance doivent être pris en compte.

Le stockage physique peut également inclure de l'espace réutilisable issu
d'anciennes écritures. La taille seule ne mesure pas précisément ce phénomène.
Aucune opération VACUUM FULL ou suppression n'est lancée par ce script.
