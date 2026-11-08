Parcours retenu pour le groupe : [installation locale de la base, sans DVC](installation-locale-equipe.md).

# Module 1 — Données et base PostgreSQL

J'ai regroupé dans ce module la préparation des sources, leur import et l'accès
à la base depuis Python. La base enedis est hébergée sur mon ordinateur Windows,
dans Ubuntu/WSL, avec PostgreSQL 16.

## Documentation actuelle

- [Dictionnaire de la base](dictionnaire-base.md) : 16 tables de données, 234 colonnes, types et suivi des imports.
- [Consignes d'installation et d'accès](consignes-installation-database.md) : environnement du groupe et connexion.
- [Interface Python](package-database.md) : fonctions et exemples.
- [Parcours Python](parcours-python.md) : création et évolution.
- [Migration des types](migration-types.md) : conversion des anciennes tables texte.
- [Décisions sur les données](decisions-traitement.md) : résultats du diagnostic.
- [Plan du module](plan-module-1.md) : objectifs et travaux restants.

## État actuel

Les données sont importées dans donnees. Le schéma database_meta suit les fichiers.
Les types ont été migrés et les comptages de consommation vérifiés.
L'accès distant des membres du groupe reste à configurer.
Les vues métier, le stockage des résultats et le versionnement des expériences
restent à compléter.
