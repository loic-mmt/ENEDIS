-- À exécuter connecté à enedis avec le rôle enedis_app, après le fichier 000.
-- Première version de développement ; les futures évolutions auront leur migration.
BEGIN;
CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS meta.import_fichier (
    id_import bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    jeu_donnees text NOT NULL,
    nom_fichier text NOT NULL,
    empreinte_sha256 text NOT NULL CHECK (length(empreinte_sha256) = 64),
    version_pipeline text NOT NULL,
    date_import timestamptz NOT NULL DEFAULT now(),
    nombre_lignes bigint NOT NULL CHECK (nombre_lignes >= 0),
    UNIQUE (jeu_donnees, empreinte_sha256, version_pipeline)
);

-- Une copie fidèle des valeurs textuelles (CSV) ou des objets source (futurs imports).
CREATE TABLE IF NOT EXISTS staging.observation (
    id_observation bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_import bigint NOT NULL REFERENCES meta.import_fichier,
    numero_enregistrement bigint NOT NULL CHECK (numero_enregistrement >= 2),
    donnees_source jsonb NOT NULL,
    UNIQUE (id_import, numero_enregistrement)
);
CREATE TABLE IF NOT EXISTS meta.anomalie (
    id_anomalie bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_import bigint NOT NULL REFERENCES meta.import_fichier,
    numero_enregistrement bigint,
    colonne text,
    description text NOT NULL
);

-- Une version historique d'un territoire, pas seulement son code actuel.
CREATE TABLE IF NOT EXISTS core.territoire (
    id_territoire bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL,
    niveau text NOT NULL CHECK (niveau IN ('commune','epci','departement','region','enedis')),
    nom text,
    debut_validite date NOT NULL,
    fin_validite date,
    geom geometry(MultiPolygon, 4326),
    CHECK (fin_validite IS NULL OR fin_validite > debut_validite),
    UNIQUE (niveau, code, debut_validite)
);
CREATE TABLE IF NOT EXISTS core.rattachement_territoire (
    id_rattachement bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_enfant bigint NOT NULL REFERENCES core.territoire,
    id_parent bigint NOT NULL REFERENCES core.territoire,
    debut_validite date NOT NULL,
    fin_validite date,
    CHECK (id_enfant <> id_parent),
    CHECK (fin_validite IS NULL OR fin_validite > debut_validite)
);

CREATE TABLE IF NOT EXISTS core.consommation_annuelle (
    id_consommation bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    id_territoire bigint REFERENCES core.territoire,
    annee integer,
    code_commune text,
    nom_commune text,
    code_epci text,
    nom_epci text,
    type_epci text,
    code_departement text,
    nom_departement text,
    code_region text,
    nom_region text,
    code_categorie_consommation text,
    code_grand_secteur text,
    code_secteur_naf2 text,
    nb_sites bigint,
    conso_totale_mwh numeric,
    conso_moyenne_mwh numeric,
    nombre_de_mailles_secretisees numeric,
    part_thermosensible numeric,
    conso_totale_usages_thermosensibles_mwh numeric,
    conso_totale_usages_non_thermosensibles_mwh numeric,
    thermosensibilite_totale_kwh_dju numeric,
    conso_totale_thermosensible_corrigee_climat_mwh numeric,
    conso_moyenne_usages_thermosensibles_mwh numeric,
    conso_moyenne_usages_non_thermosensibles_mwh numeric,
    thermosensibilite_moyenne_kwh_dju numeric,
    conso_moyenne_thermosensible_corrigee_climat_mwh numeric,
    dju_a_tr numeric,
    dju_a_tn numeric,
    nombre_d_habitants numeric,
    taux_de_logements_collectifs numeric,
    taux_de_residences_principales numeric,
    superficie_des_logements_30_m2 numeric,
    superficie_des_logements_30_a_40_m2 numeric,
    superficie_des_logements_40_a_60_m2 numeric,
    superficie_des_logements_60_a_80_m2 numeric,
    superficie_des_logements_80_a_100_m2 numeric,
    superficie_des_logements_100_m2 numeric,
    residences_principales_avant_1919 numeric,
    residences_principales_de_1919_a_1945 numeric,
    residences_principales_de_1946_a_1970 numeric,
    residences_principales_de_1971_a_1990 numeric,
    residences_principales_de_1991_a_2005 numeric,
    residences_principales_apres_2006 numeric,
    residences_principales_les_plus_recentes numeric,
    taux_de_chauffage_electrique numeric,
    code_pnr text,
    nom_pnr text,
    code_ept text,
    nom_ept text,
    CHECK (annee IS NULL OR annee BETWEEN 2011 AND 2025),
    CHECK (nb_sites IS NULL OR nb_sites >= 0)
);

-- Tables prévues pour les autres sources : aucun import fourni pour elles à ce stade.
-- id_observation donne accès à toutes les colonnes originales, même non détaillées ici.
CREATE TABLE IF NOT EXISTS core.solaire_installe (
    id_solaire bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    id_territoire bigint REFERENCES core.territoire,
    niveau_geographique text NOT NULL,
    code_territoire_source text,
    date_mesure date,
    type_installation text,
    vecteur text,
    puissance_mw numeric
);
CREATE TABLE IF NOT EXISTS core.production_regionale (
    id_production bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    id_territoire bigint REFERENCES core.territoire,
    identifiant_source text,
    code_region_source text,
    horodate timestamptz,
    horodate_source text,
    filiere text,
    tranche_puissance text,
    nombre_points_injection bigint,
    energie_wh numeric
);
CREATE TABLE IF NOT EXISTS core.point_charge_observation (
    id_point_charge_observation bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    id_territoire bigint REFERENCES core.territoire,
    id_pdc_source text,
    id_station_source text,
    code_commune_source text,
    date_observation timestamptz,
    puissance_nominale_kw numeric,
    geom geometry(Point,4326)
);
CREATE TABLE IF NOT EXISTS core.etat_point_charge (
    id_etat bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    id_pdc_source text,
    horodate timestamptz,
    etat text,
    occupation text
);
-- Pas de FK directe état → observation statique : un point peut avoir plusieurs
-- descriptions datées ou ne pas être présent dans le fichier statique.
CREATE TABLE IF NOT EXISTS core.poste_observation (
    id_poste bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    id_territoire bigint REFERENCES core.territoire,
    code_commune_source text,
    date_observation timestamptz,
    geom geometry(Point,4326)
);
CREATE TABLE IF NOT EXISTS core.statistique_reseau (
    id_statistique bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    id_territoire bigint REFERENCES core.territoire,
    maille_source text,
    code_territoire_source text,
    annee integer,
    longueur_hta_km numeric,
    longueur_bt_km numeric,
    nombre_postes bigint
);
CREATE TABLE IF NOT EXISTS core.serie_charge (
    id_serie bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    groupe text NOT NULL,
    identifiant_source text NOT NULL,
    unite text,
    UNIQUE (groupe, identifiant_source)
);
CREATE TABLE IF NOT EXISTS core.mesure_charge (
    id_mesure bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    id_serie bigint NOT NULL REFERENCES core.serie_charge,
    horodate timestamptz,
    valeur numeric
);
CREATE TABLE IF NOT EXISTS meta.consolidation_irve (
    id_consolidation bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_observation bigint NOT NULL UNIQUE REFERENCES staging.observation,
    dataset_id text,
    resource_id text,
    resource_status text,
    consolidation_status text,
    error_type text,
    error_message text
);
COMMIT;
