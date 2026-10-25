# Plan du module 1 — Traitement des données et base PostgreSQL/PostGIS

## 1. Objectif et périmètre

Le module 1 prépare des données fiables, documentées et accessibles pour les prévisions, les scénarios et l’application décrits dans [la problématique](problematique.md). Il couvre le profilage, le traitement des anomalies et valeurs manquantes, les référentiels géographiques, les imports Python/SQL et les vues de consultation.

**Conserver toutes les sources et toutes les colonnes disponibles**, même si leur utilité n’est pas encore démontrée. Cela ne signifie pas joindre tous les jeux dans une seule table : leurs échelles géographiques, leurs périodes et la signification de leurs lignes diffèrent.

Le plan s’appuie sur [data.md](data.md), [controle-donnees.md](controle-donnees.md) et les en-têtes des CSV présents. Les nombres d’anomalies cités viennent du rapport existant ; ils devront être recalculés par les futurs scripts. Le CSV de consommation est désormais présent. Ce document est une proposition de travail : il ne crée pas encore la base et ne modifie pas les données.

## 2. Organisation générale

```text
data/raw/ : fichiers reçus, conservés sans modification
       ↓ Python : inventaire, profilage et chargement par lots
staging : lignes sources et valeurs d’origine, rattachées à un import
       ↓ Python + SQL : typage, contrôles, harmonisation
core : observations structurées et référentiels
       ↓ SQL : agrégations et jointures contrôlées
analytics : vues pour les modèles et l’application

meta : sources, fichiers, imports, dictionnaire, décisions et anomalies
       accompagne chaque étape
```

Une ligne avec une mesure utilisable mais une localisation manquante reste exploitable pour certains usages. Une ligne impossible à convertir reste dans `staging`, avec une anomalie explicite. Une exclusion d’une vue d’analyse ne doit pas devenir une suppression des données sources.

## 3. Première priorité : comprendre et traiter les données manquantes

### 3.1 Faire un diagnostic reproductible avant de remplacer quoi que ce soit

Créer un script de profilage couvrant **tous les jeux**, avec lecture par morceaux pour les gros CSV et par lots pour les Parquet.

Pour chaque fichier et colonne, produire :

- nombre de lignes, type attendu, nombre et taux de valeurs vides ;
- marqueurs particuliers rencontrés, par exemple chaînes vides, `N/A` ou codes de confidentialité, à interpréter à partir du dictionnaire source ;
- valeurs non convertibles, minimum, maximum et catégories disponibles ;
- taux de manque par année, territoire et catégorie lorsque ces dimensions existent ;
- doublons exacts et répétitions des clés métier candidates ;
- périodes couvertes et trous dans les séries, en distinguant absence d’une ligne et cellule vide.

Lire d’abord les CSV en texte pour préserver les codes, les marqueurs et les zéros initiaux. Configurer explicitement les valeurs reconnues comme manquantes : les conventions automatiques de pandas ne doivent pas effacer un code valide. Les fichiers `:Zone.Identifier` sont des métadonnées Windows à ignorer dans l’import, pas des observations.

**Livrables :** un tableau de qualité par colonne, un bilan par jeu et un registre des décisions. Ne pas conclure à la confidentialité uniquement parce qu’une cellule est vide.

### 3.2 Distinguer les causes

| Situation | Décision initiale | Exemple |
| --- | --- | --- |
| Valeur réellement égale à zéro | Conserver `0` | Consommation explicitement publiée à zéro |
| Valeur absente sans cause connue | Conserver `NULL`, motif `inconnu` | Mesure non renseignée |
| Valeur masquée pour confidentialité | Conserver `NULL`, motif confirmé par la source | Mesure secretisée |
| Champ non applicable | Conserver `NULL`, motif `non_applicable` | Attribut hors du périmètre de la catégorie |
| Valeur présente mais invalide | Conserver le texte source, mettre la valeur typée à `NULL`, signaler l’erreur | Date ou nombre illisible |
| Ligne attendue mais absente | Signaler un trou de couverture | Demi-heure manquante pour une série active |
| Information récupérable dans un référentiel fiable | Corriger avec traçabilité | Code retrouvé à partir d’une correspondance officielle datée |

Ces motifs doivent être enregistrés par champ concerné, pas seulement par ligne : une observation peut avoir plusieurs problèmes différents.

### 3.3 Solutions possibles et conditions d’utilisation

| Solution | Quand l’envisager | Limites et précautions |
| --- | --- | --- |
| Garder `NULL` | Choix par défaut dans les tables d’observations | Les vues doivent exposer les taux de couverture ; ne pas présenter une somme partielle comme un total complet |
| Compléter depuis une source de référence | Correspondance vérifiable et période compatible | Conserver la source de correction et les valeurs avant/après |
| Recalculer à partir de composantes | Identité métier documentée, composantes complètes et de même périmètre | Ne pas reconstituer automatiquement une mesure protégée ; attention aux arrondis et catégories qui se recouvrent |
| Reporter la dernière valeur connue | Variable de stock, continuité justifiée et durée maximale définie | Pas de report automatique pour l’énergie consommée ; une absence ne prouve pas la stabilité du parc |
| Interpoler un petit trou | Série régulière, trou court et comportement compatible | Éviter les longues lacunes et ruptures ; le solaire varie fortement ; ne pas utiliser le futur lors d’une validation prédictive |
| Médiane d’un groupe ou modèle d’imputation | Variables explicatives et groupes comparables | Réduit parfois la variabilité ; ajuster la méthode uniquement sur les données d’entraînement |
| Écarter d’une analyse précise | Champ indispensable manquant pour cet usage | Garder la ligne ailleurs et publier le nombre de lignes écartées ainsi que le biais possible |

**Règle : aucune imputation statistique ne remplace la mesure source dans `core`.** Les estimations vont dans une table séparée ou une vue de travail, avec méthode, version, date, valeur estimée et indicateur d’imputation. Comparer les résultats avec et sans imputation avant de retenir une méthode avec les responsables des modules 2 et 3.

Pour une validation temporelle, les corrections et estimations doivent utiliser seulement les informations disponibles à la date de prévision. Conserver aussi la date d’acquisition des fichiers : une donnée publiée après cette date peut introduire une fuite d’information.

## 4. Traitements à prévoir pour chaque jeu

### 4.1 Consommation électrique communale

- Conserver toutes les colonnes : consommation, sites, catégories, secteurs, climat, habitants, logements et rattachements géographiques.
- Examiner les **446 907 consommations totales manquantes** signalées dans le rapport, selon l’année et les catégories. Utiliser notamment `Nombre de mailles secretisées` comme information de diagnostic, sans lui attribuer automatiquement la cause de chaque manque.
- Identifier le grain réel : commune, année, catégorie de consommation, grand secteur et secteur NAF2 sont des dimensions candidates à vérifier ensemble.
- Ne pas additionner totaux et sous-catégories. Définir une règle explicite pour chaque agrégation ; ne pas sommer des moyennes ou des taux.
- Conserver les années sans consommation connue ; une absence de ligne n’est pas un zéro.
- Vérifier si les attributs de population et de logement sont répétés sur plusieurs lignes sectorielles avant de créer une table communale annuelle.

### 4.2 Puissance solaire aux quatre échelles

- Importer commune, EPCI, département et région séparément ou dans une même table avec un niveau géographique explicite.
- Garder les types photovoltaïque, thermodynamique et non renseignés. Une vue pourra ensuite sélectionner le photovoltaïque.
- Conserver `date_mesure` brute et la date convertie. Isoler les dates anciennes, dont 1900, dans les contrôles ; ne pas les remplacer arbitrairement par une année récente.
- Confirmer si la date décrit un stock ou une variation avant de calculer des cumuls annuels ou de reporter une valeur.
- Garder les puissances en MW ; ne pas déduire une absence d’installation d’une ligne absente.
- Comparer les agrégations communales aux autres échelles, sans additionner les quatre fichiers entre eux. Un écart peut venir des périmètres ou de la couverture.

### 4.3 Production régionale

- Utiliser les 70 Parquet déjà disponibles ; aucun nouveau téléchargement ou changement de format n’est nécessaire.
- Lire par lots et conserver toutes les filières, tranches de puissance, courbes moyennes et indices de représentativité, y compris les valeurs textuelles comme `S`.
- Vérifier les répétitions d’identifiants sur l’ensemble du dataset et la clé métier candidate : instant, région, filière et tranche. Un identifiant technique unique ne garantit pas l’unicité métier.
- Stocker les instants en UTC et conserver l’horodatage source. Calculer les jours et années métier en `Europe/Paris` ; gérer les changements d’heure.
- Distinguer année partielle, trou dans une série et valeur manquante. Les années 2023 et 2026 sont partielles.
- Séparer dans les vues les catégories totales `P0`/`F0` de leurs détails. Ne pas additionner ni moyenner les courbes et indices sans règle documentée.
- Garder les Wh d’origine ; exposer une conversion MWh explicite lorsque nécessaire : `Wh / 1 000 000`.

### 4.4 Bornes de recharge

- Distinguer stations et points de charge ; conserver tous les attributs et les identifiants de provenance.
- Contrôler les **27 084 coordonnées signalées incorrectes**. Une borne sans coordonnées valides peut rester utilisable par code commune ; elle est simplement absente de la vue cartographique.
- Examiner les **2 répétitions d’identifiant** statique. Regrouper les copies identiques dans une représentation canonique avec toutes leurs provenances ; conserver les conflits pour arbitrage.
- Pour les **10 446 répétitions d’identifiant** dynamique, tester une clé comprenant identifiant et horodatage. Des états à des instants différents ne sont pas des doublons.
- Garder les observations dynamiques sans correspondance statique ; la jointure doit révéler les non-correspondances.
- Ne pas sommer `nbre_pdc` sur chaque ligne de point de charge si la valeur est répétée pour une station. La puissance nominale ne mesure pas l’énergie consommée ni nécessairement la puissance simultanée d’une station.
- Importer le rapport de consolidation dans les tables de suivi. L’export dynamique reste un instantané partiel, pas un historique de fréquentation.

### 4.5 Réseau électrique

- Pour les postes, conserver la géométrie source, `X`, `Y` et les rattachements géographiques.
- Pour les **15 codes commune absents**, conserver les postes et essayer un rattachement spatial seulement après validation des coordonnées et obtention de contours communaux datés.
- Vérifier le système de référence de chaque représentation avant de construire une géométrie PostGIS. Ne pas déclarer des coordonnées projetées comme longitude/latitude.
- Sans identifiant de poste stable dans le fichier, attribuer une clé interne et conserver le repère de ligne source. Deux postes proches ne sont pas nécessairement des doublons.
- Importer les statistiques de lignes à leur maille réelle : département, région ou ensemble Enedis, par année. Ne pas les transformer artificiellement en observations communales.
- Ne pas interpréter un nombre de postes ou une longueur de ligne comme une capacité électrique disponible. La proximité d’une borne et d’un poste ne démontre pas un raccordement.

### 4.6 Courbes de charge RES2

- Concaténer les deux jeux en conservant le groupe d’origine. Tester la clé `(groupe, ID, horodate)` et les éventuels identifiants communs aux groupes.
- Confirmer l’unité de `valeur`, la signification des groupes et les conditions de représentativité avant toute conversion ou extrapolation.
- Vérifier doublons, valeurs non finies et trous sur la grille temporelle attendue. Faire les contrôles d’instants en UTC pour ne pas confondre les heures répétées au changement d’heure.
- Conserver les valeurs manquantes. Une interpolation éventuelle se fait dans une version dérivée explicitement identifiée.
- Ne pas inventer de commune : aucune correspondance géographique n’est présente dans ces fichiers.

## 5. Harmoniser les territoires et les périodes

**Référentiels à acquérir en complément :** codes géographiques officiels, historique des changements communaux, rattachements datés et, pour les traitements spatiaux, contours avec leur millésime. Ils ne sont pas supposés déjà disponibles dans `data/raw/`. PVGIS reste une source future, absente de la livraison actuelle.

Conserver les codes géographiques en texte. Un code commune seul ne suffit pas à décrire un territoire à travers toutes les années : associer un millésime ou une période de validité.

Deux vues peuvent coexister :

- une vue respectant les territoires de chaque année, fidèle aux observations ;
- une vue sur un périmètre géographique constant, utile pour comparer les évolutions.

Les fusions peuvent permettre d’agréger certaines mesures additives. Une scission ne permet pas de répartir automatiquement une valeur ancienne : il faut une règle justifiée ou laisser la correspondance non résolue. Ne pas répartir par défaut la consommation au prorata de la surface. Conserver les pondérations et la méthode si une réallocation est retenue.

Ne pas injecter les bornes et postes observés aujourd’hui dans toutes les années passées. Séparer date d’observation, date d’import et date de mise en service lorsqu’elle est connue.

## 6. Proposition de structure de la base

Cette structure est indicative. Les clés uniques seront finalisées après profilage ; une contrainte trop précoce risquerait de rejeter des lignes valides.

### 6.1 Schémas et tables

| Schéma | Tables proposées | Rôle et grain |
| --- | --- | --- |
| `meta` | `source`, `fichier`, `import` | Origine, chemin, empreinte SHA-256, taille, date d’acquisition, statut et version du pipeline |
| `meta` | `dictionnaire_colonne`, `regle_qualite`, `decision_traitement` | Correspondances de noms, unités, sens des champs, règles et décisions versionnées |
| `meta` | `anomalie`, `bilan_qualite` | Problèmes par import, ligne et champ ; comptages et couverture |
| `staging` | Tables par famille de fichiers | Toutes les valeurs sources et leur repère : import, fichier et numéro de ligne ou de lot/ligne Parquet |
| `core` | `territoire_version`, `rattachement_territoire`, `correspondance_territoire` | Communes, EPCI, départements, régions et périmètre Enedis ; versions et liens datés |
| `core` | `consommation_annuelle` | Observation au grain sectoriel confirmé, avec toutes les mesures sources |
| `core` | `solaire_installe` | Territoire, date/période, type d’installation et vecteur ; puissance MW |
| `core` | `production_regionale_demiheure` | Instant, région, filière et tranche ; énergie et autres colonnes sources |
| `core` | `station_irve`, `point_charge_irve`, `observation_irve_statique` | Entités et descriptions observées lors de chaque livraison |
| `core` | `etat_point_charge` | Identifiant source, instant et état ; rattachement interne facultatif si non résolu |
| `meta` | `consolidation_irve` | Lignes du rapport, ressources sources et statuts d’import |
| `core` | `poste_electrique_observation` | Poste localisé dans un instantané, sans inventer d’historique |
| `core` | `statistique_reseau_annuelle` | Territoire, maille et année ; longueurs et nombres de postes |
| `core` | `serie_charge`, `mesure_charge` | Groupe et identifiant de série, puis instant et valeur ; unité documentée ou encore inconnue |
| `core` | `provenance_observation` | Liens entre observations structurées et une ou plusieurs lignes sources |
| `analytics` | `estimation_mesure` | Valeurs dérivées/imputées, méthode, version, observation et champ concernés |
| `analytics` | Vues d’analyse | Données adaptées à chaque usage, avec périmètre et couverture explicites |

Conserver les mesures fréquemment interrogées en colonnes typées. Les champs sources supplémentaires peuvent d’abord rester dans `staging` en texte ou JSONB, puis être promus dans `core` selon les besoins. Le dictionnaire doit permettre de retrouver chaque colonne d’origine ; aucune colonne ne disparaît silencieusement.

### 6.2 Relations principales

```text
source → fichier → import → lignes staging
                              ↓ provenance
territoire_version ← observations consommation / solaire / réseau / production
        ↑
rattachements datés et correspondances entre millésimes

station IRVE → points de charge → observations statiques et états dynamiques
série de charge → mesures horodatées

observations + référentiels → vues analytics
imports et observations → anomalies, bilans et décisions
```

Les références géographiques non résolues restent facultatives : conserver le code source et signaler l’anomalie au lieu de supprimer la ligne. Les courbes RES2 restent indépendantes des territoires tant qu’aucune correspondance fiable n’existe.

### 6.3 Vues à proposer aux autres modules

- `v_consommation_commune_annee` : consommation selon une règle sectorielle validée, nombre de mesures attendues/connues et complétude.
- `v_solaire_commune_annee` : puissance photovoltaïque selon la définition temporelle validée ; ne pas sommer aveuglément les dates d’une année.
- `v_equipement_commune_snapshot` : points de charge et postes à la date d’observation, avec couverture géographique.
- `v_production_regionale_jour` : énergie par jour et catégories retenues, nombre de demi-heures attendues/connues et couverture.
- `v_panel_commune_annee` : consommation et solaire sur un référentiel commun, puis variables complémentaires compatibles avec l’année étudiée.
- `v_qualite_sources` : manque, anomalies, doublons et correspondances géographiques non résolues.

Construire le panel avec une grille de territoires/périodes ou une jointure conservant les observations non appariées, plutôt qu’une jointure interne qui ferait disparaître silencieusement des communes. Les caractéristiques d’équipement actuelles restent dans une vue séparée tant qu’un historique fiable n’est pas établi.

En SQL, `SUM` ignore les valeurs `NULL` : afficher `SUM(valeur)` avec `COUNT(valeur)` et `COUNT(*)`. Un total partiel doit être nommé comme tel ; ne pas employer `COALESCE(valeur, 0)` pour masquer les manques. La couverture temporelle exige aussi de comparer aux créneaux attendus, pas seulement aux lignes présentes.

## 7. Comment procéder à la création de la base

### Étape A — Préparer les outils et les décisions

Utiliser Python pour lire/profiler les fichiers et PostgreSQL/PostGIS pour stocker, contrôler et joindre les données. Ajouter un pilote PostgreSQL au projet au moment de l’implémentation. Garder les paramètres de connexion hors du code et versionner seulement un exemple de configuration sans mot de passe.

Décider de l’environnement local, du nom de base, du référentiel géographique et du format des rapports. Dimensionner le stockage avec un import pilote : les fichiers occupent plusieurs Go, et les tables, index, sauvegardes et journaux nécessiteront davantage d’espace.

### Étape B — Créer une base de développement

Créer une base dédiée, activer PostGIS avec un compte autorisé, puis appliquer une migration SQL initiale. Les commandes suivantes illustrent les schémas ; elles ne définissent pas encore toutes les tables :

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;
```

Séparer le compte de chargement du compte de lecture utilisé par les modèles et l’application. Prévoir une sauvegarde et un essai de restauration avant de dépendre de la base pour le travail collectif.

### Étape C — Charger les sources en staging

Commencer par un petit fichier solaire, puis passer à la consommation et aux grandes séries.

1. Enregistrer le fichier et son empreinte, puis ouvrir un import avec statut `en_cours`.
2. Lire les CSV par morceaux et les Parquet par lots ; ne pas tout charger en RAM.
3. Charger via `COPY` les colonnes sources et les repères de provenance. Pour Parquet, Python transmet les lots : ne pas supposer que PostgreSQL lit directement ces fichiers avec `COPY`.
4. Vérifier les comptages et clôturer l’import en succès ou en échec.
5. Reconnaître un fichier déjà chargé grâce à son empreinte. Un nouvel import ne doit pas dupliquer les observations publiées.

Ne pas écraser une livraison précédente lorsqu’une source évolue. Séparer les versions et choisir explicitement celle exposée par les vues pour éviter de compter plusieurs livraisons du même jeu.

### Étape D — Construire les tables core

Créer les référentiels et les tables avec types explicites : codes en texte, années entières, mesures numériques, dates, `timestamptz` pour les instants et géométries avec SRID confirmé.

Transformer les valeurs, garder les manques en `NULL`, enregistrer les anomalies et les corrections. N’ajouter les contraintes d’unicité métier qu’après résolution des répétitions. Utiliser des clés internes pour les observations et conserver les identifiants sources séparément.

Publier une nouvelle version seulement après validation. Un échec doit laisser la version précédente consultable. Pour les gros imports, charger et valider dans des tables ou partitions de travail avant publication, plutôt qu’ouvrir une transaction unique sur tout le projet.

### Étape E — Ajouter contraintes et performances

Ajouter clés étrangères sur les correspondances résolues, contraintes de cohérence confirmées et index sur codes, dates et identifiants fréquemment joints. Ajouter un index spatial GiST pour les géométries utilisées dans les recherches spatiales.

La production régionale et les courbes représentent plusieurs dizaines de millions de lignes. Envisager un partitionnement temporel si les mesures de performance le justifient ; la clé unique d’une table partitionnée doit être conçue avec sa clé de partition. Ne pas indexer toutes les colonnes par défaut.

### Étape F — Créer et valider les vues

Vérifier l’unicité au grain de sortie et les cardinalités avant/après jointure. Une relation plusieurs-à-plusieurs peut multiplier les lignes et gonfler les sommes. Comparer les agrégats aux sources, exposer les limites et fournir quelques requêtes d’exemple aux autres membres du groupe.

## 8. Organisation possible des futurs fichiers

Ces chemins sont proposés, pas encore créés par ce document.

```text
scripts/
  profile_data.py             # inventaire et rapport de qualité
  ingest_data.py              # lancement des imports
src/enedis/ingestion/
  common.py                  # lectures par lots et traçabilité
  consommation.py
  solaire.py
  production.py
  irve.py
  reseau.py
  courbes_charge.py
sql/
  001_schemas_meta.sql
  002_staging.sql
  003_referentiels.sql
  004_tables_core.sql
  005_vues_analytics.sql
  006_controles.sql
docs/
  dictionnaire-donnees.md
  decisions-traitement.md
data/processed/
  rapports/                  # rapports générés, sans modifier raw
```

Versionner les scripts, migrations, définitions et décisions. Garder les exports volumineux hors de Git selon les règles du projet.

## 9. Ordre de travail et livrables

| Phase | Travail | Critère pour passer à la suite |
| --- | --- | --- |
| 1 — Profilage | Inventorier tous les fichiers et calculer les manques, anomalies et clés candidates | Rapport reproductible pour chaque source, sans imputation automatique |
| 2 — Règles | Dictionnaire, causes des manques, unités, grains et décisions provisoires | Chaque traitement a une justification ; les inconnues restent signalées |
| 3 — Base pilote | Créer les schémas et importer un petit fichier solaire de bout en bout | Provenance, comptages et relance sans duplication validés |
| 4 — Toutes les sources | Charger tous les jeux en staging puis core, y compris les métadonnées et rapports | Chaque ligne est traçable vers une observation ou une anomalie, sans perte silencieuse |
| 5 — Harmonisation | Référentiels datés, géométries, doublons et correspondances | Taux de correspondance et conflits documentés |
| 6 — Vues | Panel communal et vues propres à chaque échelle | Unicité, unités, temporalité et agrégations vérifiées |
| 7 — Livraison | Documentation, scripts, bilan de qualité et exemples SQL | Un autre membre peut reconstruire et interroger la base |

La priorité de démarrage est la consommation et le solaire communal, car ils alimentent les deux prévisions principales. Cela fixe l’ordre d’exécution, **pas une exclusion des autres jeux** : toutes les sources restent dans le périmètre d’import et de documentation.

## 10. Vérifications de fin de module

- Les fichiers bruts restent intacts ; toutes les colonnes sont conservées et documentées.
- Les comptages distinguent lignes sources, copies exactes, observations canoniques, conflits et lignes non convertibles. Ils se réconcilient à chaque étape selon des règles explicites.
- Aucune confidentialité ou absence inconnue n’est convertie automatiquement en zéro.
- Les mesures observées restent distinctes des estimations et des corrections.
- Les clés uniques sont validées ; les jointures ne multiplient pas les observations.
- Les géométries, unités, fuseaux, périodes partielles et changements de communes sont pris en compte.
- Les relances sont possibles sans doublons et un import échoué ne remplace pas une version valide.
- Les modèles reçoivent des vues documentées avec couverture et limites, sans utilisation silencieuse d’informations futures.

Le module est livrable même si certaines données restent manquantes : l’objectif est de savoir lesquelles, pourquoi si possible, pour quels usages elles restent exploitables et quelles décisions ont été prises.
