# Dictionnaire de la base enedis

## État documenté

La base est hébergée sur mon ordinateur Windows, dans Ubuntu/WSL, avec PostgreSQL 16. Ce dictionnaire reprend les 234 colonnes des 16 tables du schéma donnees, d'après l'export information_schema transmis après migration des types. Il décrit cet état constaté ; les changements ultérieurs doivent être répercutés dans ce document.

Le schéma database_meta assure le suivi des imports. Sa définition ci-dessous provient du code du package ; elle n'était pas incluse dans cet export des colonnes.

## Organisation

| Schéma | Rôle |
| --- | --- |
| donnees | Sources importées et colonnes de provenance |
| database_meta | Suivi des fichiers et correspondances de noms |
| public | Schéma PostgreSQL par défaut, sans table métier constatée dans cet inventaire |

Le package Python définit les objets des schémas donnees et database_meta.

## Types et valeurs manquantes

- numeric : nombre décimal ; integer/bigint : entier.
- double precision : nombre flottant, utilisé notamment dans les Parquet de production.
- date : date civile ; timestamp with time zone : instant horodaté.
- text : code, identifiant, libellé ou champ source non encore converti.
- jsonb : document JSON.
- NULL désigne une absence ; zéro reste une valeur distincte.
- Toutes les colonnes de donnees autorisent NULL dans l'état observé. Cela ne signifie pas qu'elles en contiennent toutes.
- Les codes géographiques restent text afin de préserver notamment les zéros initiaux.

## Tables de données

| Table | Rôle | Colonnes |
| --- | --- | ---: |
| charge_res2_6_9 | Mesures horodatées des séries du groupe RES2-6-9. | 5 |
| charge_res2_9_12 | Mesures horodatées des séries du groupe RES2-9-12. | 5 |
| consommation_annuelle | Consommations annuelles par commune, catégorie et secteur. | 51 |
| dictionnaire_solaire | Définitions des champs du jeu solaire. | 4 |
| documents_source | Documents JSON de métadonnées et de conversion. | 3 |
| documents_texte | Documents texte de description des sources. | 3 |
| irve_dynamique | États et occupations horodatés des points de recharge. | 10 |
| irve_rapport | Rapport de consolidation des ressources IRVE. | 14 |
| irve_statique | Descriptions et caractéristiques des points de recharge. | 51 |
| postes_electriques | Localisation et rattachements géographiques des postes. | 15 |
| production_regionale | Production horodatée par région, filière et plage de puissance. | 23 |
| solaire_commune | Puissance solaire publiée à la maille communale. | 8 |
| solaire_departement | Puissance solaire publiée à la maille départementale. | 8 |
| solaire_epci | Puissance solaire publiée à la maille EPCI. | 8 |
| solaire_region | Puissance solaire publiée à la maille régionale. | 8 |
| statistiques_reseau | Statistiques annuelles de lignes et de postes par maille. | 18 |

## donnees.charge_res2_6_9

Mesures horodatées des séries du groupe RES2-6-9.

Source dans data/raw : courbes_de_charge/RES2-6-9.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| id | text | Oui |
| horodate | timestamp with time zone | Oui |
| valeur | numeric | Oui |

Index définis dans le package : index sur _source_file; index sur (id, horodate). Leur présence effective se vérifie dans pg_indexes.


## donnees.charge_res2_9_12

Mesures horodatées des séries du groupe RES2-9-12.

Source dans data/raw : courbes_de_charge/RES2-9-12.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| id | text | Oui |
| horodate | timestamp with time zone | Oui |
| valeur | numeric | Oui |

Index définis dans le package : index sur _source_file; index sur (id, horodate). Leur présence effective se vérifie dans pg_indexes.


## donnees.consommation_annuelle

Consommations annuelles par commune, catégorie et secteur.

Source dans data/raw : consommation/consommation-electrique-par-secteur-dactivite-commune.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| annee | integer | Oui |
| code_commune | text | Oui |
| nom_commune | text | Oui |
| code_epci | text | Oui |
| nom_epci | text | Oui |
| type_epci | text | Oui |
| code_departement | text | Oui |
| nom_departement | text | Oui |
| code_region | text | Oui |
| nom_region | text | Oui |
| code_categorie_consommation | text | Oui |
| code_grand_secteur | text | Oui |
| code_secteur_naf2 | text | Oui |
| nb_sites | bigint | Oui |
| conso_totale_mwh | numeric | Oui |
| conso_moyenne_mwh | numeric | Oui |
| nombre_de_mailles_secretisees | numeric | Oui |
| part_thermosensible | numeric | Oui |
| conso_totale_usages_thermosensibles_mwh | numeric | Oui |
| conso_totale_usages_non_thermosensibles_mwh | numeric | Oui |
| thermosensibilite_totale_kwh_dju | numeric | Oui |
| conso_totale_corrigee_de_l_alea_climatique_usages__88db8cd06861 | numeric | Oui |
| conso_moyenne_usages_thermosensibles_mwh | numeric | Oui |
| conso_moyenne_usages_non_thermosensibles_mwh | numeric | Oui |
| thermosensibilite_moyenne_kwh_dju | numeric | Oui |
| conso_moyenne_corrigee_de_l_alea_climatique_usages_b5dfccaa86ba | numeric | Oui |
| dju_a_tr | numeric | Oui |
| dju_a_tn | numeric | Oui |
| nombre_d_habitants | numeric | Oui |
| taux_de_logements_collectifs | numeric | Oui |
| taux_de_residences_principales | numeric | Oui |
| superficie_des_logements_30_m2 | numeric | Oui |
| superficie_des_logements_30_a_40_m2 | numeric | Oui |
| superficie_des_logements_40_a_60_m2 | numeric | Oui |
| superficie_des_logements_60_a_80_m2 | numeric | Oui |
| superficie_des_logements_80_a_100_m2 | numeric | Oui |
| superficie_des_logements_100_m2 | numeric | Oui |
| residences_principales_avant_1919 | numeric | Oui |
| residences_principales_de_1919_a_1945 | numeric | Oui |
| residences_principales_de_1946_a_1970 | numeric | Oui |
| residences_principales_de_1971_a_1990 | numeric | Oui |
| residences_principales_de_1991_a_2005 | numeric | Oui |
| residences_principales_apres_2006 | numeric | Oui |
| residences_principales_les_plus_recentes | numeric | Oui |
| taux_de_chauffage_electrique | numeric | Oui |
| code_pnr | text | Oui |
| nom_pnr | text | Oui |
| code_ept | text | Oui |
| nom_ept | text | Oui |

Index définis dans le package : index sur _source_file; index sur (code_commune, annee). Leur présence effective se vérifie dans pg_indexes.


## donnees.dictionnaire_solaire

Définitions des champs du jeu solaire.

Source dans data/raw : puissance_photovoltaique/description-des-champs.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| colonne | text | Oui |
| description | text | Oui |

Index définis dans le package : index sur _source_file. Leur présence effective se vérifie dans pg_indexes.


## donnees.documents_source

Documents JSON de métadonnées et de conversion.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| document | jsonb | Oui |

Index définis dans le package : index sur _source_file. Leur présence effective se vérifie dans pg_indexes.


## donnees.documents_texte

Documents texte de description des sources.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| contenu | text | Oui |

Index définis dans le package : index sur _source_file. Leur présence effective se vérifie dans pg_indexes.


## donnees.irve_dynamique

États et occupations horodatés des points de recharge.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| id_pdc_itinerance | text | Oui |
| etat_pdc | text | Oui |
| occupation_pdc | text | Oui |
| horodatage | timestamp with time zone | Oui |
| etat_prise_type_2 | text | Oui |
| etat_prise_type_combo_ccs | text | Oui |
| etat_prise_type_chademo | text | Oui |
| etat_prise_type_ef | text | Oui |

Index définis dans le package : index sur _source_file; index sur (id_pdc_itinerance, horodatage). Leur présence effective se vérifie dans pg_indexes.


## donnees.irve_rapport

Rapport de consolidation des ressources IRVE.

Source dans data/raw : bornes_recharge/consolidation_transport_irve_statique_rapport.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| dataset_id | text | Oui |
| resource_id | text | Oui |
| resource_status | text | Oui |
| consolidation_status | text | Oui |
| error_type | text | Oui |
| estimated_pdc_count | bigint | Oui |
| file_extension | text | Oui |
| url | text | Oui |
| dataset_title | text | Oui |
| datagouv_organization_or_owner | text | Oui |
| datagouv_last_modified | text | Oui |
| error_message | text | Oui |

Index définis dans le package : index sur _source_file. Leur présence effective se vérifie dans pg_indexes.


## donnees.irve_statique

Descriptions et caractéristiques des points de recharge.

Source dans data/raw : bornes_recharge/consolidation_transport_irve_statique.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| nom_amenageur | text | Oui |
| siren_amenageur | text | Oui |
| contact_amenageur | text | Oui |
| nom_operateur | text | Oui |
| contact_operateur | text | Oui |
| telephone_operateur | text | Oui |
| nom_enseigne | text | Oui |
| id_station_itinerance | text | Oui |
| id_station_local | text | Oui |
| nom_station | text | Oui |
| implantation_station | text | Oui |
| adresse_station | text | Oui |
| code_insee_commune | text | Oui |
| coordonneesxy | text | Oui |
| nbre_pdc | bigint | Oui |
| id_pdc_itinerance | text | Oui |
| id_pdc_local | text | Oui |
| puissance_nominale | numeric | Oui |
| prise_type_ef | text | Oui |
| prise_type_2 | text | Oui |
| prise_type_combo_ccs | text | Oui |
| prise_type_chademo | text | Oui |
| prise_type_autre | text | Oui |
| gratuit | text | Oui |
| paiement_acte | text | Oui |
| paiement_cb | text | Oui |
| paiement_autre | text | Oui |
| tarification | text | Oui |
| condition_acces | text | Oui |
| reservation | text | Oui |
| horaires | text | Oui |
| accessibilite_pmr | text | Oui |
| restriction_gabarit | text | Oui |
| station_deux_roues | text | Oui |
| raccordement | text | Oui |
| num_pdl | text | Oui |
| date_mise_en_service | text | Oui |
| observations | text | Oui |
| date_maj | text | Oui |
| cable_t2_attache | text | Oui |
| consolidated_longitude | numeric | Oui |
| consolidated_latitude | numeric | Oui |
| consolidated_is_lon_lat_correct | text | Oui |
| datagouv_dataset_id | text | Oui |
| datagouv_resource_id | text | Oui |
| dataset_title | text | Oui |
| datagouv_organization_or_owner | text | Oui |
| datagouv_last_modified | text | Oui |
| deduplication_status | text | Oui |

Index définis dans le package : index sur _source_file; index sur (id_pdc_itinerance). Leur présence effective se vérifie dans pg_indexes.


## donnees.postes_electriques

Localisation et rattachements géographiques des postes.

Source dans data/raw : reseau/poste-electrique.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| geometry | text | Oui |
| x | numeric | Oui |
| y | numeric | Oui |
| code_iris | text | Oui |
| nom_iris | text | Oui |
| code_commune | text | Oui |
| nom_commune | text | Oui |
| code_epci | text | Oui |
| nom_epci | text | Oui |
| code_departement | text | Oui |
| nom_departement | text | Oui |
| code_region | text | Oui |
| nom_region | text | Oui |

Index définis dans le package : index sur _source_file; index sur (code_commune). Leur présence effective se vérifie dans pg_indexes.


## donnees.production_regionale

Production horodatée par région, filière et plage de puissance.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| horodate | timestamp with time zone | Oui |
| region | text | Oui |
| code_region | text | Oui |
| plage_de_puissance_injection | text | Oui |
| filiere_de_production | text | Oui |
| nb_points_injection | bigint | Oui |
| total_energie_injectee_wh | double precision | Oui |
| courbe_moyenne_ndeg1_wh | double precision | Oui |
| indice_representativite_courbe_ndeg1 | text | Oui |
| courbe_moyenne_ndeg2_wh | double precision | Oui |
| indice_representativite_courbe_ndeg2 | text | Oui |
| courbe_moyenne_ndeg1_ndeg2_wh | double precision | Oui |
| indice_representativite_courbe_ndeg1_ndeg2 | text | Oui |
| jour_max_du_mois_0_1 | text | Oui |
| semaine_max_du_mois_0_1 | text | Oui |
| id | text | Oui |
| i | bigint | Oui |
| rand | bigint | Oui |
| horodate_source | text | Oui |
| score | double precision | Oui |
| year | bigint | Oui |

Index définis dans le package : index sur _source_file; index sur (code_region, horodate). Leur présence effective se vérifie dans pg_indexes.


## donnees.solaire_commune

Puissance solaire publiée à la maille communale.

Source dans data/raw : puissance_photovoltaique/puissance-solaire-installee-commune.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| date_mesure | date | Oui |
| geocode_commune | text | Oui |
| libelle_commune | text | Oui |
| type_installation | text | Oui |
| vecteur | text | Oui |
| valeur | numeric | Oui |

Index définis dans le package : index sur _source_file; index sur (geocode_commune, date_mesure). Leur présence effective se vérifie dans pg_indexes.


## donnees.solaire_departement

Puissance solaire publiée à la maille départementale.

Source dans data/raw : puissance_photovoltaique/puissance-solaire-installee-departement.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| date_mesure | date | Oui |
| geocode_departement | text | Oui |
| libelle_departement | text | Oui |
| type_installation | text | Oui |
| vecteur | text | Oui |
| valeur | numeric | Oui |

Index définis dans le package : index sur _source_file; index sur (geocode_departement, date_mesure). Leur présence effective se vérifie dans pg_indexes.


## donnees.solaire_epci

Puissance solaire publiée à la maille EPCI.

Source dans data/raw : puissance_photovoltaique/puissance-solaire-installee-epci.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| date_mesure | date | Oui |
| geocode_epci | text | Oui |
| libelle_epci | text | Oui |
| type_installation | text | Oui |
| vecteur | text | Oui |
| valeur | numeric | Oui |

Index définis dans le package : index sur _source_file; index sur (geocode_epci, date_mesure). Leur présence effective se vérifie dans pg_indexes.


## donnees.solaire_region

Puissance solaire publiée à la maille régionale.

Source dans data/raw : puissance_photovoltaique/puissance-solaire-installee-region.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| date_mesure | date | Oui |
| geocode_region | text | Oui |
| libelle_region | text | Oui |
| type_installation | text | Oui |
| vecteur | text | Oui |
| valeur | numeric | Oui |

Index définis dans le package : index sur _source_file; index sur (geocode_region, date_mesure). Leur présence effective se vérifie dans pg_indexes.


## donnees.statistiques_reseau

Statistiques annuelles de lignes et de postes par maille.

Source dans data/raw : reseau/donnees-relatives-aux-lignes-et-aux-postes.csv.

| Colonne | Type PostgreSQL | NULL autorisé |
| --- | --- | --- |
| _source_file | text | Oui |
| _imported_at | timestamp with time zone | Oui |
| maille_geographique | text | Oui |
| departement_region_enedis | text | Oui |
| code_departement | text | Oui |
| code_region | text | Oui |
| annee | integer | Oui |
| hta_souterrain_km | numeric | Oui |
| hta_aerien_nu_km | numeric | Oui |
| hta_aerien_tors_km | numeric | Oui |
| hta_total_km | numeric | Oui |
| nb_postes_hta_bt | bigint | Oui |
| bt_souterrain | numeric | Oui |
| bt_aerien_torsade | numeric | Oui |
| bt_aerien_nu | numeric | Oui |
| bt_total_km | numeric | Oui |
| pourcentage_ouvrages_faible_taux_d_incidents | numeric | Oui |
| total_km | numeric | Oui |

Index définis dans le package : index sur _source_file. Leur présence effective se vérifie dans pg_indexes.

## database_meta.fichier

Définition issue de Database.initialize(), à distinguer de l'export constaté ci-dessus.

| Colonne | Type | NULL autorisé |
| --- | --- | --- |
| schema_name | text | Non |
| table_name | text | Non |
| source_file | text | Non |
| sha256 | text | Non |
| rows_count | bigint | Non |
| imported_at | timestamp with time zone | Non |
| columns_mapping | jsonb | Non |

Clé primaire composée : (schema_name, table_name, source_file).
Le suivi mémorise le dernier état importé d'un chemin, pas un historique complet de ses versions.

## Relations et contraintes

Les tables donnees n'ont pas de clés étrangères ni de clés métier uniques créées par l'import générique. Les rapprochements devront tenir compte du territoire, de la période, du secteur et de l'échelle. Commune + année ne suffit pas à identifier une ligne de consommation.
Les index de lecture sont non uniques. Aucun lien automatique n'est imposé entre les tables.
Les colonnes _source_file et _imported_at indiquent la provenance et l'instant d'import.

## Limites de typage restantes

Les dates secondaires et indicateurs de l'IRVE restent en texte. geometry dans postes_electriques reste du texte : aucune géométrie PostGIS n'a été construite. Les dates solaires 1900-01-01 sont conservées ; leur interprétation reste à valider. Les unités doivent être confirmées dans les dictionnaires sources, notamment pour les courbes de charge.

## Contrôles réalisés

La consommation contient 3 763 258 lignes, dont 446 907 valeurs manquantes et 606 401 zéros pour conso_totale_mwh. La production régionale contient 34 089 984 lignes. Les comptages de consommation ont été confirmés après migration. Ces contrôles ne valident pas à eux seuls les doublons métier ou les correspondances géographiques.

## Actualisation du dictionnaire

Relever les colonnes avec la requête suivante dans psql :

    SELECT table_schema, table_name, column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema IN ('donnees', 'database_meta')
    ORDER BY table_schema, table_name, ordinal_position;

Vérifier les index avec :

    SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes
    WHERE schemaname IN ('donnees', 'database_meta');
