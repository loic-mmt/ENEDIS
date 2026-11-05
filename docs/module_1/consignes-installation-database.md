# Consignes installation database — guide pour toute l'équipe

Ce guide décrit le parcours Python enedis.database (donnees / database_meta).
Ne pas exécuter les anciens SQL de sql/module_1 pour ce parcours.
Aucune commande d'installation ou de création n'a été exécutée pendant sa rédaction.

## 1. Choisir où sera la base commune

Une seule machine héberge PostgreSQL et la base enedis. Chacun a une copie du
code et son environnement Python, mais tous se connectent à cette même base.
Git partage le code ; il ne partage pas les données PostgreSQL.

Choisir un serveur universitaire ou une machine dédiée accessible au groupe.
Ta WSL peut héberger un prototype, mais ton ordinateur et WSL devront rester
allumés et accessibles pour les autres. Installer PostgreSQL chez chacun crée
des bases indépendantes : cela ne les synchronise pas.

Le groupe doit fixer : responsable, adresse du serveur, port, nom de base,
accès réseau privé/VPN ou SSH, comptes et sauvegardes. Ces paramètres ne sont
pas encore choisis dans le dépôt.

## 2. Ce que chacun installe

| Outil | Responsable serveur/import | Collègues |
| --- | --- | --- |
| Serveur PostgreSQL | Oui, une fois | Non |
| Git, dépôt commun | Oui | Oui |
| Python >= 3.10, environnement virtuel | Oui | Oui |
| Package enedis avec extra database | Oui | Oui |
| Données brutes | Sur la machine d'import | Pas nécessaires pour lire |
| psql | Utile pour administrer | Facultatif |
| DBeaver / pgAdmin | Facultatif | Facultatif |
| PostGIS | Plus tard pour le spatial | Non |

Le parcours actuel n'utilise pas PostGIS.

## 3. Installer PostgreSQL — responsable seulement

Exemple sur Ubuntu, sur la machine serveur :

    sudo apt update
    sudo apt install postgresql postgresql-client python3-venv git
    sudo service postgresql start
    sudo -u postgres createuser --login --createdb --pwprompt enedis_owner

La dernière commande est à faire une seule fois si le rôle n'existe pas.
Le compte enedis_owner sera réservé aux imports et évolutions communes.
Si l'université fournit la base, demander un compte propriétaire et suivre
ses consignes au lieu d'installer un second serveur.

## 4. Installer le package — chacun

Récupérer le dépôt commun avec Git. Depuis sa racine, dans Ubuntu/WSL :

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e '.[database]'
    python -c "from enedis.database import Database; print('Package disponible')"

Si .venv existe, simplement l'activer puis installer le package.
Sous Windows natif : python -m venv .venv puis
.venv/Scripts/python.exe -m pip install -e ".[database]".

Cette installation fournit numpy, pandas, psycopg et pyarrow selon pyproject.toml.
Si une version n'est pas disponible, conserver l'erreur pour ajuster ensemble
la compatibilité ; ne pas considérer les dépendances comme déjà testées.

L'installation editable rend src/enedis importable dans tout script lancé
avec CE Python. Dans Jupyter/VS Code, choisir aussi cet environnement.

Organisation du code :
- src/enedis/database : connexion, tables, imports et lectures ;
- src/enedis/prediction : modèles ;
- src/enedis/scenarios : scénarios.

Pour rendre une fonction publique, l'exposer dans le __init__.py du sous-package.
Après git pull, le code éditable est actualisé. Réinstaller avec pip si les
dépendances changent. Mettre à jour le code ne modifie pas automatiquement la base.

## 5. Créer la base — responsable seulement

Depuis la machine serveur, avec le package installé :

    export PGHOST=localhost
    export PGPORT=5432
    export PGDATABASE=enedis
    export PGUSER=enedis_owner
    read -rsp 'Mot de passe PostgreSQL : ' PGPASSWORD
    export PGPASSWORD
    python scripts/module_1/preparer_base.py --create-database enedis

Cela crée la base si absente, les schémas donnees/database_meta et le suivi
database_meta.fichier. Cela n'importe pas les sources.
Si la base existe déjà, omettre --create-database enedis.
Le script ne crée ni le serveur, ni les comptes, ni l'accès réseau.

## 6. Importer les données — une personne désignée

Configurer les mêmes paramètres PG*, puis :

    python scripts/module_1/preparer_base.py --import-all --raw /chemin/absolu/data/raw
    unset PGPASSWORD

Remplacer le chemin par le dossier réel. Les tables sources sont créées pendant
l'import ; les index de consultation sont ajoutés à la fin de l'import global.

Conserver un emplacement d'import stable : un autre chemin peut être considéré
comme une autre livraison. Les collègues ne doivent pas chacun réimporter leur copie.
Un fichier inchangé au même chemin est ignoré. Un fichier modifié remplace ses
anciennes lignes. Un échec annule le fichier courant, pas les imports précédents.
Prévoir de l'espace pour tables, index et journaux au-delà des fichiers compressés.

Les CSV sont en texte par défaut et les cellules vides deviennent NULL.
Les Parquet conservent leurs types.
Pour typer les CSV à la première création, utiliser import_existing_data avec
csv_types dans un script Python ; cette option n'existe pas encore dans la CLI.
Une table déjà créée en texte exige ensuite une migration de types.

## 7. Permettre aux collègues de se connecter

L'administration des comptes/réseau reste à faire une fois par le responsable.

Option tunnel SSH : si un serveur SSH accessible et des comptes sont disponibles,
chaque collègue garde ouvert ce terminal :

    ssh -N -L 15432:127.0.0.1:5432 compte_ssh@adresse_du_serveur

Il utilise PGHOST=127.0.0.1 et PGPORT=15432. Le tunnel mène bien à la base distante.
Cette commande ne rend pas à elle seule ta WSL accessible depuis Internet.

Option réseau privé/VPN : l'administrateur configure listen_addresses,
pg_hba.conf et le pare-feu pour les clients autorisés. Les valeurs dépendent
de l'hébergement. Éviter d'ouvrir PostgreSQL à toutes les adresses.

Exemple de compte lecteur, après création et import, dans
sudo -u postgres psql -d enedis sur le serveur :

    CREATE ROLE collegue LOGIN;
    \password collegue
    GRANT CONNECT ON DATABASE enedis TO collegue;
    GRANT USAGE ON SCHEMA donnees TO collegue;
    GRANT SELECT ON ALL TABLES IN SCHEMA donnees TO collegue;
    ALTER DEFAULT PRIVILEGES FOR ROLE enedis_owner IN SCHEMA donnees
        GRANT SELECT ON TABLES TO collegue;

Remplacer collegue par chaque compte individuel. Les droits futurs ci-dessus
concernent les tables créées par enedis_owner.
Les lecteurs utilisent read_table ; ils ne lancent ni initialize ni les imports.

Pour simplifier le démarrage, le propriétaire exécute les évolutions communes.
Les comptes d'écriture de résultats et leurs droits devront être configurés
et testés avant usage. Le package ne gère pas encore ces permissions.
Ne pas partager le compte propriétaire avec toute l'équipe.

## 8. Lire depuis n'importe quel script Python

Configurer PGHOST/PGPORT selon le mode d'accès, puis :

    export PGDATABASE=enedis
    export PGUSER=collegue
    read -rsp 'Mot de passe PostgreSQL : ' PGPASSWORD
    export PGPASSWORD

Alternative : ~/.pgpass sous Linux/WSL (chmod 600 ~/.pgpass) ou
%APPDATA%/postgresql/pgpass.conf sous Windows.
Format : hote:port:base:utilisateur:mot_de_passe. Garder ce fichier hors de Git.

Exemple Python disponible aujourd'hui :

    from enedis.database import Database

    with Database() as db:
        df = db.read_table(
            "consommation_annuelle",
            columns=["code_commune", "annee", "conso_totale_mwh"],
            filters={"code_commune": "35238", "annee": "2024"},
            limit=1000,
        )

df est un DataFrame. L'année est une chaîne avec les imports CSV par défaut.
Les filtres actuels sont des égalités ; la limite par défaut est 1000 sans ordre
garanti. limit=None charge toute la sélection en mémoire : ne pas l'utiliser
sur toute la production. Lectures par période, lots et version restent à développer.

## 9. Ajouter des colonnes sans écrire de SQL

Conserver la définition dans un fichier Python versionné, puis faire exécuter
la configuration par le propriétaire des tables :

    from enedis.database import Database

    COLONNES = {
        "experience": "text",
        "code_commune": "text",
        "annee": "integer",
        "prediction_mwh": "numeric",
    }

    with Database() as db:
        db.configure_table(
            "predictions_exemple",
            COLONNES,
            required=["experience", "code_commune", "annee"],
            indexes=[{
                "columns": ["experience", "code_commune", "annee"],
                "unique": True,
            }],
        )

Cet exemple suppose UNE valeur par expérience, commune et année. Pour des
résultats par catégorie/secteur, ajouter ces dimensions à la clé.

Le lendemain, ajouter au dictionnaire :

    COLONNES["intervalle_bas_mwh"] = "numeric"
    COLONNES["intervalle_haut_mwh"] = "numeric"

Puis relancer la même configuration. Les colonnes absentes sont ajoutées ;
les anciennes lignes y ont NULL. Le nom et le type sont nécessaires : changer
uniquement un nombre de colonnes ne définit pas ce qu'elles représentent.

Un champ obligatoire ne peut pas être imposé si les lignes existantes ont NULL.
Une erreur annule la configuration. Retirer une colonne du dictionnaire ne la
supprime pas. Renommer/changer de type/modifier une ancienne contrainte nécessite
une migration. Coordonner les modifications d'une table partagée via Git.

Stocker les prédictions dans des tables séparées : un réimport des sources
pourrait effacer les enrichissements ajoutés à leurs lignes.

## 10. Estimer les consommations NULL

Oui, une valeur manquante peut être estimée si les informations disponibles
le permettent. C'est une imputation ; une prévision concerne une période future.

1. Garder NULL dans la consommation observée.
2. Entraîner sur des cibles connues et des caractéristiques disponibles.
3. Évaluer sur des observations connues mises de côté, avec une séparation
   temporelle adaptée ; éviter les informations futures indisponibles à la date
   de prévision.
4. Appliquer le modèle aux lignes manquantes admissibles.
5. Enregistrer l'estimation séparément, avec modèle, expérience et incertitude.

Une ligne absente du fichier n'est pas la même chose qu'une ligne avec NULL.
Les absences liées à la confidentialité ne sont pas nécessairement aléatoires :
la performance sur valeurs connues ne garantit pas celle sur les valeurs cachées.
L'estimation ne devient pas une mesure officielle.

Lecture d'un échantillon des lignes manquantes :

    with Database() as db:
        a_estimer = db.read_table(
            "consommation_annuelle",
            filters={"conso_totale_mwh": None},
            limit=1000,
        )

Ce n'est pas un traitement exhaustif ; une lecture par lots reste à développer.

La table durable d'estimations devra identifier : observation source et version,
commune, année, catégorie, secteur/NAF2, estimation_mwh, type imputation/prévision,
expérience, modèle, date limite d'apprentissage, date du calcul et incertitude.
Commune + année seules ne suffisent pas à identifier une ligne de consommation.

Le package ne fournit pas encore d'identifiant stable de ligne ni d'historique
complet des versions. Les définir avant de stocker durablement les résultats.
Un futur affichage pourra choisir la mesure si connue, sinon l'estimation,
avec une colonne explicite indiquant l'origine.

## 11. Disponible et restant à développer

Disponible dans le code : connexion, création de base, imports, ajout de colonnes,
configuration des champs obligatoires/index et lecture limitée en DataFrame.

À développer : enregistrer_predictions, enregistrer_imputations, insertions de
DataFrames, lectures par lots/période, vues métier et versions des expériences.
Créer une table de résultats ne suffit pas encore à y enregistrer un DataFrame.

Les corrections récentes ont eu une vérification syntaxique ; les comportements
doivent encore être validés sur PostgreSQL. Tester d'abord une petite base dédiée :
connexion depuis un second ordinateur, droits, import, relance sans doublon,
ajout de colonne et annulation d'un import invalide.

Tests sans serveur, après installation :

    python -m unittest discover -s tests -p test_database_files.py -v

Le responsable prévoit des sauvegardes et vérifie leur restauration. Exemple :

    pg_dump -Fc -d enedis -f enedis.dump

Utiliser les paramètres PG* du compte autorisé ; conserver les sauvegardes hors
du dépôt, sur un autre support que le serveur.

## Références

- [Authentification et accès PostgreSQL](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html)
- [Fichier de mots de passe PostgreSQL](https://www.postgresql.org/docs/current/libpq-pgpass.html)
- [Interface du projet](package-database.md)
