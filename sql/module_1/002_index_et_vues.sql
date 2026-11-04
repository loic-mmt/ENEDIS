BEGIN;
CREATE INDEX IF NOT EXISTS consommation_commune_annee_idx
    ON core.consommation_annuelle (code_commune, annee);
CREATE INDEX IF NOT EXISTS territoire_geom_idx ON core.territoire USING gist (geom);
CREATE INDEX IF NOT EXISTS production_region_date_idx
    ON core.production_regionale (code_region_source, horodate);
CREATE INDEX IF NOT EXISTS point_charge_geom_idx
    ON core.point_charge_observation USING gist (geom);
CREATE INDEX IF NOT EXISTS poste_geom_idx ON core.poste_observation USING gist (geom);
CREATE INDEX IF NOT EXISTS etat_point_charge_source_date_idx
    ON core.etat_point_charge (id_pdc_source, horodate);
CREATE INDEX IF NOT EXISTS mesure_charge_serie_date_idx
    ON core.mesure_charge (id_serie, horodate);

-- Consultation détaillée, sans somme ni estimation des valeurs manquantes.
-- Chaque import reste identifiable pour ne pas mélanger plusieurs livraisons.
CREATE OR REPLACE VIEW analytics.consommation_detail AS
SELECT c.*, o.id_import, o.numero_enregistrement,
       c.conso_totale_mwh IS NULL AS consommation_manquante
FROM core.consommation_annuelle c
JOIN staging.observation o USING (id_observation);

CREATE OR REPLACE VIEW analytics.suivi_imports AS
SELECT i.*, (SELECT count(*) FROM staging.observation o
             WHERE o.id_import = i.id_import) AS lignes_source_en_base
FROM meta.import_fichier i;
COMMIT;
