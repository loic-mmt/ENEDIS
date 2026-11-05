**Mise a jour types :** les CSV connus sont desormais types automatiquement. Pour une base deja importee, suivre [la migration](migration-types.md) avant tout nouvel import. Cette consigne remplace les mentions de CSV tous en texte ci-dessous.

# Parcours commun retenu : package Python

Le point d'entree est enedis.database. Le script scripts/module_1/preparer_base.py
utilise les schemas donnees et database_meta. Les definitions et les commandes SQL
sont gerees dans src/enedis/database.

## Objets créés par le parcours
- La base demandee par --create-database, si absente et si le compte a CREATEDB.
- Le schema donnees et le suivi database_meta.fichier.
- Avec --import-all : tables de consommation, solaire par echelle, production
  regionale, IRVE, reseau, deux groupes de courbes et documents source.
- Colonnes originales normalisees, _source_file et _imported_at.
- Index de provenance et index territoire/date ou identifiant/date sur les
  principales sources. Les index metier sont crees apres un import global reussi.

Sans --import-all, le script cree seulement les schemas et le suivi.
Le serveur PostgreSQL, les comptes et le reseau doivent deja etre configures.
La base du projet a été créée et alimentée dans WSL. Les commandes suivantes décrivent sa reconstruction.

## Commande commune
Depuis la racine, apres installation du serveur :
    .venv/bin/python -m pip install -e '.[database]'
    .venv/bin/python scripts/module_1/preparer_base.py --create-database enedis --import-all

Configurer les variables PG* et les droits avant execution. --create-database
selectionne maintenant aussi cette base pour la connexion de travail.
Pour une base existante, configurer PGDATABASE et omettre --create-database.

## Faire evoluer une table depuis Python
    from enedis.database import Database
    with Database() as db:
        db.configure_table("resultats", {
            "experience": "text",
            "code_commune": "text",
            "annee": "integer",
            "prediction_mwh": "numeric",
        }, required=["experience", "code_commune", "annee"],
           indexes=[{"columns": ["experience", "code_commune", "annee"], "unique": True}])

Ajouter une entree au dictionnaire ajoute une colonne ; les anciennes lignes
recoivent NULL. Les contraintes sont verifiees sur les donnees existantes.
Une erreur annule cette configuration. Un index ne change pas simplement parce
qu'une ancienne definition est retiree : suppressions, renommages et changements
de types demandent une migration explicite. Un nombre de colonnes seul ne suffit pas.

## Limites explicites
Les CSV restent en texte par defaut. Fournir csv_types a import_existing_data
pour typer une premiere importation ; une table deja en texte exige une migration.
Les index sur dates textuelles ne remplacent pas une conversion temporelle.
Aucune cle metier unique n'est imposee aux sources sans validation des doublons.
Les imports sont transactionnels par fichier, pas sur tout le catalogue.
Un fichier modifie au meme chemin remplace sa livraison precedente : ce parcours
ne fournit pas encore de versions historiques reproductibles.
Conserver features, predictions et enrichissements dans des tables distinctes.
read_table reste une lecture limitee (1000 par defaut), avec filtres d'egalite.
Les vues metier, lectures par periode et par lots, ecritures de resultats et suivi
d'experiences restent a developper et a tester sur PostgreSQL.
