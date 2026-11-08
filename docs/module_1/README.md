# Module 1 — Données et base PostgreSQL

Ce module regroupe la préparation des sources, leur import et l'accès depuis Python.
Chaque membre dispose d'une copie locale nommée enedis. La base de référence a
été préparée dans Ubuntu/WSL ; le guide d'installation couvre macOS et Windows.

## Documentation

- [Installation locale et utilisation Python](installation-locale-equipe.md) : guide unique pour le groupe.
- [Dictionnaire de la base](dictionnaire-base.md) : 16 tables de données, 234 colonnes, types et suivi des imports.
- [Migration des types](migration-types.md) : réparation des anciennes bases importées en texte.
- [Décisions sur les données](decisions-traitement.md) : résultats du diagnostic.
- [Plan du module](plan-module-1.md) : objectifs et travaux.

## État actuel

Les sources sont importées dans donnees ; database_meta suit les fichiers.
Le script installer_base_locale.py contrôle la conformité des sources et reconstruit
la base avec les types actuels. Les modifications locales ne se synchronisent pas.
Les définitions Python sont partagées par Git et appliquées sur chaque poste.
Les vues métier, le stockage des résultats et le versionnement des expériences
restent à compléter.

- [Audit fichiers/base et espace disque](audit-imports.md) : contrôles de provenance, volumes et index.
