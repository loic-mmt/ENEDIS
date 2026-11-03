-- Requêtes de lecture uniquement. À lancer APRÈS l'import.
SELECT * FROM analytics.suivi_imports ORDER BY id_import;

SELECT o.id_import,
       count(*) AS lignes_consommation,
       count(*) FILTER (WHERE c.conso_totale_mwh IS NULL) AS consommations_manquantes,
       count(*) FILTER (WHERE c.nb_sites IS NULL) AS nombres_sites_manquants
FROM core.consommation_annuelle c
JOIN staging.observation o USING (id_observation)
GROUP BY o.id_import;

SELECT id_import, code_commune, annee, code_categorie_consommation,
       code_grand_secteur, code_secteur_naf2, count(*) AS occurrences
FROM analytics.consommation_detail
GROUP BY id_import, code_commune, annee, code_categorie_consommation,
         code_grand_secteur, code_secteur_naf2
HAVING count(*) > 1;
