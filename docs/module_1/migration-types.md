# Migration des types apres import

Les CSV connus utilisent maintenant les types de src/enedis/database/definitions.py.
La consommation (mesures numeric, annee integer, nb_sites bigint), les puissances
solaires, les mesures de charge, les mesures reseau et certaines mesures IRVE
sont typees. Les codes restent text. Les autres champs non specifies restent text.
La production Parquet, deja typee, n'est pas migree.
Les noms existants, y compris les noms longs normalises, restent identiques.

## Procedure dans Ubuntu/WSL : Que pour moi comme j'ai un Window
Quitter psql avec \q, activer .venv a la racine du projet.
Conserver les variables PGHOST, PGPORT, PGDATABASE=enedis et PGUSER=enedis_owner.
Configurer le mot de passe via .pgpass ou saisie interactive PGPASSWORD.

1. Terminer les imports et interrompre les ecritures concurrentes.
2. Sauvegarder hors du depot, avec assez d'espace :
       pg_dump -Fc -d enedis -f ~/enedis-avant-types.dump
   Attendre un code retour nul avant de continuer.
3. Controle sans alteration des tables :
       python scripts/module_1/migrer_types.py
4. Si toutes les conversions sont valides :
       python scripts/module_1/migrer_types.py --apply
5. Verifier dans psql :
       \d donnees.consommation_annuelle
       SELECT count(*), count(*) FILTER (WHERE conso_totale_mwh IS NULL),
              count(*) FILTER (WHERE conso_totale_mwh = 0)
       FROM donnees.consommation_annuelle;
   References de la livraison actuelle : 3763258 / 446907 / 606401.

Ne pas relancer un import avant migration des tables existantes.
Apres migration, les imports utilisent les memes definitions automatiquement.
Pour filtrer une annee avec read_table, utiliser 2024 (entier), plus "2024".
Ne pas utiliser btrim sur une colonne devenue numeric.

## Garanties et limites
Controle et conversion utilisent les casts PostgreSQL. Une valeur non convertible
arrete le traitement et indique la colonne et le nombre de valeurs concernees.
Les zeros sont conserves ; aucune imputation ou suppression.
Pas de remplacement automatique des virgules decimales : une valeur incompatible
doit etre examinee. Les fichiers actuels utilisent notamment le point decimal.
Les conversions sont transactionnelles PAR TABLE. Les tables precedemment
validees restent converties si une table suivante echoue. Relancer est possible :
les colonnes conformes sont ignorees. --table consommation_annuelle permet de cibler.
Un ALTER TABLE regroupe les conversions d'une meme table.
Le mode --apply verrouille la table pendant controle et conversion.
Le verrou attend au maximum 5 secondes ; sa conversion peut ensuite etre longue.
Les comptages totaux et non nuls sont compares avant/apres dans la transaction.
PostgreSQL reconstruit les index concernes. Un echec annule la table courante.
Prevoir de l'espace libre pour la reecriture, les index et les journaux.
Les dates solaires 1900-01-01 sont conservees ; leur sens metier reste a verifier.
Ces modifications corrigent les types, pas les regles de qualite metier.

Tests sans serveur : python -m unittest discover -s tests -p 'test_database*.py' -v
Les tests d'integration sur un serveur PostgreSQL restent a executer.
