# Installation locale de la base ENEDIS

## Organisation retenue

Chaque membre dispose d'une base PostgreSQL locale nommée enedis. La structure,
les types et les données sources sont les mêmes que ceux de la base de référence.
Aucun DVC, Google Drive, VPN, SSH ou hébergement payant n'est nécessaire.
Les copies sont indépendantes : une colonne ou un résultat ajouté sur un poste
n'apparaît pas automatiquement sur les autres.

Le script scripts/module_1/installer_base_locale.py utilise le package enedis.database.
Il reconstruit les tables depuis les fichiers déjà disponibles, sans sauvegarde à
restaurer. Les chemins de provenance et les dates d'import diffèrent entre postes.
Les empreintes des fichiers sont comparées à reference_base.json, et les types
aux 234 colonnes de l'export de référence après migration.

## 1. Installer les prérequis

Sur tous les postes : Git, Python (3.12 conseillé pour s'aligner sur le projet),
PostgreSQL 16 ou plus récent. Un même majeur PostgreSQL simplifie les comparaisons.
PostGIS, DVC et pgAdmin ne sont pas obligatoires ; pgAdmin est facultatif pour visualiser.

Téléchargements officiels :
- https://www.python.org/downloads/
- https://www.postgresql.org/download/macos/
- https://www.postgresql.org/download/windows/
- https://git-scm.com/downloads

Sur macOS, choisir une distribution PostgreSQL indiquée sur la page officielle,
démarrer le serveur et relever le nom du compte administrateur créé.
Certains installateurs utilisent postgres ; d'autres utilisent le nom de session macOS.

Sur Windows, installer PostgreSQL avec son serveur (pgAdmin seul ne suffit pas).
Conserver le port choisi, généralement 5432, et le mot de passe du compte postgres.
Le service PostgreSQL doit être démarré.

L'installation système n'est pas automatisée par le script Python : elle nécessite
les choix et droits d'administration propres au poste.

Prévoir au moins 40 Go libres comme marge de départ, davantage si les sources,
les fichiers temporaires et les résultats sont sur le même disque. La base de
référence occupait environ 17 Go après import ; la taille locale peut varier.

## 2. Récupérer la bonne version du projet

Cloner le dépôt commun avec Git, ou exécuter git pull dans une copie existante.
Toutes les étapes suivantes se font à la racine du dépôt, là où se trouve pyproject.toml.
Conserver la même version Git dans le groupe pour reproduire le même schéma.

Les sources doivent être présentes dans data/raw avec l'arborescence d'origine.
Le script détecte les fichiers manquants, supplémentaires ou différents.
Les fichiers Windows :Zone.Identifier sont ignorés.
Un fichier différent ne doit pas être remplacé à l'aveugle : comparer la livraison.

## 3. Installer l'environnement Python

### macOS — Terminal

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e '.[database]'

Si .venv existe déjà, l'activer sans le recréer.

### Windows — PowerShell

    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e ".[database]"

L'utilisation directe de python.exe évite de changer la politique d'exécution
PowerShell pour activer un environnement.

Ces commandes installent le package et ses dépendances PostgreSQL/Parquet.
Ne pas installer requirements-dvc.txt pour ce parcours.
En cas d'erreur de dépendance, arrêter et transmettre le message.

## 4. Vérifier les fichiers sans toucher à PostgreSQL

Sur Mac :

    python scripts/module_1/installer_base_locale.py --check-files

Sur Windows :

    .\.venv\Scripts\python.exe scripts/module_1/installer_base_locale.py --check-files

Le calcul SHA-256 lit toutes les sources et peut prendre quelques minutes.
Le message « Sources conformes » indique que les fichiers correspondent à la
référence, pas que la base est déjà créée.

Pour des sources rangées ailleurs, ajouter --raw "/chemin/vers/data/raw".
Conserver ensuite ce chemin stable : il sert au suivi des imports.

## 5. Créer et alimenter la base

Sur Mac  :

    python scripts/module_1/installer_base_locale.py --user postgres

Sur Windows :

    .\.venv\Scripts\python.exe scripts/module_1/installer_base_locale.py --user postgres

Le script demande le mot de passe sans l'afficher ni l'enregistrer dans Git.
Laisser vide seulement si le compte local est configuré sans mot de passe.
Le compte doit pouvoir créer une base et les tables. Le propriétaire sera le
compte choisi ; il n'est pas nécessaire que son nom soit identique entre postes.

Paramètres facultatifs : --host 127.0.0.1 --port 5432.
La base s'appelle toujours enedis et le schéma source donnees.

Le script :
1. vérifie les empreintes des sources ;
2. vérifie la version du serveur et crée enedis si elle est absente ;
3. prépare donnees et database_meta ;
4. importe les fichiers avec les types de definitions.py ;
5. crée les index du catalogue ;
6. compare colonnes/types et comptages à la référence ;
7. vérifie les NULL et zéros de consommation.

Les codes restent en texte ; mesures en numeric, années en integer, effectifs
en bigint selon le dictionnaire. Les types Parquet sont conservés.
Les zéros ne sont pas transformés en NULL.

L'import peut être long : garder le terminal et le serveur ouverts.
Les fichiers sont transactionnels individuellement : une erreur annule le fichier
courant, mais les imports précédents restent validés. Une relance au même chemin
ignore les fichiers inchangés. Aucun --force n'est nécessaire.

Si une ancienne base comporte encore des colonnes texte, ne pas la supprimer :
utiliser le guide migration-types.md. Si la base a été restaurée depuis un autre
poste, lancer d'abord --verify-only ; le script refuse un nouvel import depuis
des chemins différents pour éviter une duplication des livraisons.

## 6. Contrôler à nouveau sans importer

Sur Mac :

    python scripts/module_1/installer_base_locale.py --user postgres --verify-only

Sur Windows :

    .\.venv\Scripts\python.exe scripts/module_1/installer_base_locale.py --user postgres --verify-only

Ce mode ne crée pas de base, de table ou d'index.
Le contrôle compte toutes les lignes et peut prendre du temps.
Références : consommation 3 763 258 lignes ; production 34 089 984 ;
consommation manquante 446 907 et consommation égale à zéro 606 401.
Le détail des colonnes figure dans dictionnaire-base.md.
Des colonnes ajoutées ensuite aux tables sources seront signalées comme différentes :
ce contrôle décrit la référence initiale, pas toutes les évolutions futures.

## 7. Utiliser les fonctions depuis les scripts

Configurer la connexion dans le terminal avant les analyses.

Mac :

    export PGHOST=127.0.0.1
    export PGPORT=5432
    export PGDATABASE=enedis
    export PGUSER=postgres
    read -s PGPASSWORD
    export PGPASSWORD

Après read -s PGPASSWORD, saisir le mot de passe puis Entrée.
Sous PowerShell :

    $env:PGHOST = "127.0.0.1"
    $env:PGPORT = "5432"
    $env:PGDATABASE = "enedis"
    $env:PGUSER = "postgres"
    $credential = Get-Credential -UserName postgres -Message "Connexion PostgreSQL locale"
    $env:PGPASSWORD = $credential.GetNetworkCredential().Password

Adapter le compte et le port. Ces paramètres concernent le terminal courant.
Le mot de passe ne doit pas être inscrit dans un script versionné.

Exemple Python :

    from enedis.database import Database

    with Database() as db:
        df = db.read_table(
            "consommation_annuelle",
            filters={"annee": 2024},
            limit=1000,
        )

Le DataFrame est limité à 1000 lignes, sans ordre garanti. L'année est un entier.
Utiliser le Python de .venv aussi dans l'éditeur ou le notebook.
Après usage, retirer le mot de passe du terminal avec unset PGPASSWORD sur Mac,
ou Remove-Item Env:PGPASSWORD sous PowerShell.

## 8. Faire évoluer les tables en équipe

Les définitions de tables et les fonctions restent dans src/enedis/database.
Pour partager une nouvelle colonne, versionner le changement Python dans Git,
puis exécuter la même configuration sur chaque copie locale.

Exemple de table de résultats indépendante :

    with Database() as db:
        db.configure_table(
            "resultats_exemple",
            {"experience": "text", "code_commune": "text",
             "annee": "integer", "prediction_mwh": "numeric"},
        )

Ajouter une entrée au dictionnaire, puis relancer, ajoute la colonne manquante.
Les anciennes lignes reçoivent NULL. Un renommage ou changement de type exige
une migration. Les résultats ne sont pas automatiquement partagés par Git :
prévoir des exports séparés pour les échanges.
Le package ne propose pas encore une fonction générale d'écriture de DataFrames.

## Limites de validation

Le contrôle valide les fichiers sources, les types et les volumes attendus.
Il ne prouve pas à lui seul la validité métier de chaque observation.
Les index sont créés par le même catalogue ; la suite de tests d'intégration
multiplateforme reste à compléter. La base existante n'est pas modifiée pendant
la préparation de ce guide et du script.

## Référence rapide du package Python

Les fonctions sont accessibles depuis enedis.database après installation du package.

| Fonction | Utilisation |
| --- | --- |
| Database() | Connexion PostgreSQL, à utiliser avec with |
| create_database() | Création d'une base absente ; utilisée par le script d'installation |
| db.create_table() / db.add_columns() | Création et ajout de colonnes |
| db.configure_table() | Colonnes, champs obligatoires et index dans une transaction |
| db.read_table() | Lecture en DataFrame, filtres d'égalité, limite par défaut 1000 |
| db.import_csv() / db.import_parquet() | Import d'une source supplémentaire |
| import_existing_data() | Import des fichiers d'un dossier |
| create_source_indexes() | Index de consultation des tables sources |

Les types des CSV connus sont définis dans src/enedis/database/definitions.py.
Les champs non définis restent en texte. Les Parquet utilisent leurs types sources.
Les colonnes de provenance _source_file et _imported_at sont réservées.

Exemple d'ajout de colonne :

    from enedis.database import Database

    with Database() as db:
        db.add_columns("resultats_exemple", {"incertitude_mwh": "numeric"})

Exemple d'import d'une nouvelle source, distinct de la reconstruction de référence :

    with Database() as db:
        db.import_csv(
            "/chemin/meteo.csv",
            table="meteo",
            delimiter=";",
            types={"temperature": "numeric", "date_mesure": "date"},
        )

Le chemin identifie la livraison. Un fichier modifié remplace ses anciennes
lignes dans une transaction ; les fichiers précédents restent validés si un
autre import échoue. Un fichier déplacé peut devenir une autre livraison.
Les colonnes calculées ne doivent pas être stockées dans les tables sources :
le remplacement des lignes ferait perdre ces enrichissements.
Les fonctions de lecture par lots et d'écriture générale des résultats restent
à développer. Les suppressions, renommages et changements de types nécessitent
des migrations explicites.

La [migration des types](migration-types.md) concerne uniquement les bases
créées avant le typage automatique. Le [dictionnaire](dictionnaire-base.md)
décrit les tables et colonnes de référence.
