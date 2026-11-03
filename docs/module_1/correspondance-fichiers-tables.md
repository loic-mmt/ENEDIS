# Quel fichier va dans quelle table, et pourquoi ?

Ce document explique le lien entre les fichiers reçus dans `data/raw/` et les tables prévues dans la base `enedis`.

**Les tables sont définies dans les fichiers SQL, mais leur création et les imports n’ont pas été lancés lors de leur préparation. Seul le script d’import de consommation est disponible pour le moment.**

## 1. Les données du projet

Les chemins de la colonne « Fichier source » sont relatifs à `data/raw/`.

| Fichier source | Table prévue | Que représente une ligne dans la table ? | Objectif |
| --- | --- | --- | --- |
| `consommation/consommation-electrique-par-secteur-dactivite-commune.csv` | `core.consommation_annuelle` | Une observation pour une commune, une année et une combinaison de catégories/secteurs | Conserver les consommations, nombres de sites et informations complémentaires pour les analyses et les prévisions |
| `puissance_photovoltaique/puissance-solaire-installee-commune.csv` | `core.solaire_installe` | Une mesure de puissance solaire pour une commune, une date et un type d’installation | Étudier le développement du solaire communal |
| `puissance_photovoltaique/puissance-solaire-installee-epci.csv` | `core.solaire_installe` | Une mesure de puissance solaire pour un EPCI, une date et un type d’installation | Étudier le solaire à l’échelle intercommunale |
| `puissance_photovoltaique/puissance-solaire-installee-departement.csv` | `core.solaire_installe` | Une mesure de puissance solaire pour un département, une date et un type d’installation | Comparer les départements |
| `puissance_photovoltaique/puissance-solaire-installee-region.csv` | `core.solaire_installe` | Une mesure de puissance solaire pour une région, une date et un type d’installation | Comparer les régions et rapprocher puissance installée et production |
| `production_regionale/year=AAAA/part-NNNNN.parquet` — les 70 fichiers | `core.production_regionale` | Une observation de production à un instant, pour une région, une filière et une tranche de puissance | Étudier la production électrique et ses variations temporelles |
| `bornes_recharge/consolidation_transport_irve_statique.csv` | `core.point_charge_observation` | La description d’un point de charge dans une livraison | Localiser les bornes et connaître leurs caractéristiques |
| `bornes_recharge/consolidation-nationale-irve-dynamique-2026-10-16T16_14_52.180053Z.csv` | `core.etat_point_charge` | Un état horodaté de point de charge | Étudier l’état et l’occupation indiqués dans cet export, sans supposer un historique complet |
| `bornes_recharge/consolidation_transport_irve_statique_rapport.csv` | `meta.consolidation_irve` | Un résultat de consolidation d’une ressource source | Comprendre les erreurs et les limites de couverture des données de bornes |
| `reseau/poste-electrique.csv` | `core.poste_observation` | Un poste électrique décrit dans une livraison | Cartographier les postes et les compter par territoire |
| `reseau/donnees-relatives-aux-lignes-et-aux-postes.csv` | `core.statistique_reseau` | Des statistiques pour une maille géographique et une année | Étudier les longueurs de lignes et les nombres de postes à l’échelle publiée |
| `courbes_de_charge/RES2-6-9.csv` et `courbes_de_charge/RES2-9-12.csv` | `core.serie_charge` et `core.mesure_charge` | Une série identifiée dans la première table ; ses valeurs horodatées dans la seconde | Étudier et comparer les profils de charge en gardant le groupe d’origine |

### Pourquoi plusieurs fichiers peuvent aller dans la même table ?

- **Production :** les 70 Parquet sont des morceaux du même jeu de données. Ils alimenteront une seule table logique.
- **Solaire :** les quatre CSV décrivent le même type de mesure à des échelles différentes. La colonne `niveau_geographique` distinguera commune, EPCI, département et région. Il ne faudra pas additionner ces échelles entre elles.
- **Courbes de charge :** les deux CSV ont la même structure. La colonne `groupe` permettra de distinguer leur origine.

### Pourquoi un fichier peut alimenter plusieurs tables ?

Dans les courbes de charge, l’identifiant et le groupe décrivent une **série** ; l’horodatage et la valeur décrivent ses **mesures**. On crée donc une série, puis on lui rattache ses nombreuses mesures.

Pour toutes les observations importées, on conservera aussi une copie source et la provenance, comme expliqué ci-dessous.

## 2. Les tables de suivi et de conservation

Ces tables accompagnent les imports. Elles ne représentent pas des mesures électriques supplémentaires.

| Table | D’où viennent ses informations ? | Objectif | État du premier import |
| --- | --- | --- | --- |
| `meta.import_fichier` | Informations générées par le script : nom du fichier, empreinte, date, version et comptage | Savoir quel fichier a été chargé et éviter de réimporter la même version | Remplissage prévu par `import_consommation.py` |
| `staging.observation` | Chaque enregistrement source avec toutes ses colonnes | Conserver les valeurs d’origine et pouvoir retrouver une observation avant conversion | Remplissage prévu pour la consommation |
| `meta.anomalie` | Résultats de contrôles à enregistrer par les futurs traitements | Garder une trace des problèmes avec le fichier, l’enregistrement et la colonne concernés | Table prévue ; le premier import ne la remplit pas automatiquement |

Exemple pour le CSV de consommation :

```text
CSV de consommation
    ├── meta.import_fichier : une entrée décrivant cet import
    ├── staging.observation : chaque ligne avec ses valeurs d’origine
    └── core.consommation_annuelle : les mêmes observations avec des types SQL
```

Ces copies ont des rôles différents. **On ne doit pas les additionner ni les considérer comme deux jeux de consommation.** Les analyses utiliseront la table `core` ou une vue de consultation.

## 3. Les tables géographiques

| Table | Source attendue | Objectif |
| --- | --- | --- |
| `core.territoire` | Référentiel géographique officiel daté, et contours si disponibles — à acquérir/valider | Identifier les communes, EPCI, départements et régions avec leur période de validité |
| `core.rattachement_territoire` | Correspondances géographiques datées issues de ce référentiel | Savoir, par exemple, à quel département appartient une commune pour une période donnée |

Les codes présents dans les CSV seront conservés, mais ne suffisent pas à construire un historique géographique officiel complet. Tant que le référentiel n’est pas chargé, `id_territoire` peut rester `NULL` sans empêcher l’import des observations.

Les contours ne sont pas inventés à partir des noms ou des codes. Les positions de bornes et de postes ne remplacent pas les contours communaux.

## 4. Les fichiers qui servent à décrire les données

Ces fichiers ne correspondent pas à des observations électriques à ajouter aux tables de mesures.

| Fichier | Utilisation prévue |
| --- | --- |
| `puissance_photovoltaique/description-des-champs.csv` | Lire les définitions des colonnes et les unités ; conserver le dictionnaire avec la source. Aucune table dédiée n’est créée actuellement |
| `production_regionale/metadata.json` | Comprendre les colonnes et catégories du jeu de production ; conserver les métadonnées |
| `production_regionale/_schema.txt` | Vérifier les types attendus dans les Parquet |
| `production_regionale/_conversion.json` | Conserver le bilan de conversion et ses limites |
| Fichiers terminant par `:Zone.Identifier` | Métadonnées Windows à ignorer pour l’import des observations |

Les rapports CSV générés dans `data/processed/rapports/` servent à expliquer la qualité des données. Ils ne sont pas importés comme des consommations ou des productions.

## 5. Les vues : consulter les tables plus facilement

Une vue est une requête enregistrée dans la base. Elle utilise les tables existantes ; elle ne provient pas d’un nouveau fichier CSV.

| Vue | Tables utilisées | Objectif |
| --- | --- | --- |
| `analytics.consommation_detail` | `core.consommation_annuelle` et `staging.observation` | Lire la consommation avec sa provenance et un indicateur de valeur manquante |
| `analytics.suivi_imports` | `meta.import_fichier` et `staging.observation` | Consulter les fichiers importés et les nombres d’enregistrements conservés |

Ces vues ne font aucune estimation ni agrégation de consommation. Il faudra choisir un `id_import` pour ne pas mélanger plusieurs livraisons du même jeu.

## 6. Quel script et quel SQL utiliser ?

| Fichier du projet | Ce qu’il fait |
| --- | --- |
| [000_creation_base.sql](../../sql/module_1/000_creation_base.sql) | Crée l’utilisateur, la base `enedis` et l’extension PostGIS |
| [001_structure_base.sql](../../sql/module_1/001_structure_base.sql) | Crée toutes les tables décrites ici |
| [002_index_et_vues.sql](../../sql/module_1/002_index_et_vues.sql) | Ajoute les index et les vues de consultation |
| [003_verification_import.sql](../../sql/module_1/003_verification_import.sql) | Vérifie les comptages et recherche les clés répétées après l’import |
| [colonnes_consommation.json](../../sql/module_1/colonnes_consommation.json) | Associe chaque nom de colonne du CSV de consommation à son nom et à son type SQL |
| [import_consommation.py](../../scripts/module_1/import_consommation.py) | Charge uniquement la consommation, avec ses valeurs manquantes en `NULL` |

**Les scripts d’import du solaire, de la production, des bornes, du réseau, des courbes et des référentiels restent à écrire.** Leurs tables sont une première structure : certaines colonnes typées pourront être ajoutées, tandis que les autres attributs sources resteront accessibles dans `staging.observation`.

Pour les commandes : [installation-base.md](installation-base.md). Pour les relations entre tables : [schema-base.md](schema-base.md).
