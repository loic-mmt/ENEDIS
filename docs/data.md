# Comprendre nos données

Fichiers dans `data/raw/`. Les 70 Parquet de production régionale forment un seul jeu : ils sont décrits ensemble.

## Consommation électrique

- **`consommation/consommation-electrique-par-secteur-dactivite-commune.csv`**
  - **Contenu :** consommation annuelle en MWh, nombre de sites et secteurs d’activité par commune. Certaines colonnes décrivent aussi les habitants, logements, chauffage et sensibilité au climat.
  - **Utilité :** prévoir la consommation annuelle et comparer les évolutions des communes et des secteurs.
  - **Attention :** données manquantes ou confidentielles ; choisir les catégories à additionner pour éviter les doubles comptes. Les informations sur les logements ne sont pas renseignées partout.

## Puissance solaire installée

- **`puissance_photovoltaique/puissance-solaire-installee-commune.csv`**
  - **Contenu :** puissance solaire installée en MW, par commune, date et type d’installation.
  - **Utilité :** construire la cible de prévision du développement photovoltaïque communal et mesurer sa croissance.

- **`puissance_photovoltaique/puissance-solaire-installee-epci.csv`**
  - **Contenu :** même indicateur, regroupé par intercommunalité.
  - **Utilité :** travailler à une échelle plus large et comparer les intercommunalités.

- **`puissance_photovoltaique/puissance-solaire-installee-departement.csv`**
  - **Contenu :** même indicateur, regroupé par département.
  - **Utilité :** étudier les tendances départementales et comparer les résultats agrégés des communes.

- **`puissance_photovoltaique/puissance-solaire-installee-region.csv`**
  - **Contenu :** même indicateur, regroupé par région.
  - **Utilité :** comparer les parcs régionaux et les rapprocher de la production solaire régionale.

- **`puissance_photovoltaique/description-des-champs.csv`**
  - **Contenu :** définition des colonnes, codes géographiques et unité MW.
  - **Utilité :** interpréter les quatre fichiers ; ce n’est pas une table d’observations pour les modèles.

Les MW décrivent le parc installé, pas l’électricité produite. Vérifier les dates anciennes, la période représentée par `date_mesure` et les types d’installation : tous ne sont pas photovoltaïques.

## Production électrique régionale

- **`production_regionale/year=AAAA/part-NNNNN.parquet` — 70 fichiers, années 2023 à 2026**
  - **Contenu :** énergie injectée en Wh par demi-heure, région, filière et plage de puissance ; nombre de points d’injection, courbes moyennes et indices de représentativité.
  - **Utilité :** étudier les profils de production selon l’heure et la saison, isoler le solaire, prévoir la production régionale ou alimenter des scénarios horaires.
  - **Attention :** périmètre du réseau Enedis ; ce n’est pas toute la production française. Les années 2023 et 2026 sont partielles. Ne pas additionner les totaux `P0`/`F0` avec leurs catégories détaillées.

- **`production_regionale/metadata.json`**
  - **Contenu :** description du jeu source, colonnes, catégories et unités.
  - **Utilité :** comprendre et documenter les données ; pas une entrée de modèle.

- **`production_regionale/_schema.txt`**
  - **Contenu :** noms et types des colonnes Parquet.
  - **Utilité :** préparer les lectures et vérifier la compatibilité des traitements.

- **`production_regionale/_conversion.json`**
  - **Contenu :** comptages, partitions, bornes temporelles et validation de conversion.
  - **Utilité :** contrôler la livraison des données ; pas une mesure électrique.

## Bornes de recharge

- **`bornes_recharge/consolidation_transport_irve_statique.csv`**
  - **Contenu :** points de charge, identifiants, communes, coordonnées, puissance nominale, prises et conditions d’accès.
  - **Utilité :** cartographier l’offre de recharge, compter les points par territoire et construire des indicateurs d’électrification.
  - **Attention :** certaines coordonnées et certains identifiants demandent vérification. La puissance nominale n’est pas la consommation réelle ; ne pas sommer un nombre de points de station répété sur plusieurs lignes.

- **`bornes_recharge/consolidation-nationale-irve-dynamique-2026-10-16T16_14_52.180053Z.csv`**
  - **Contenu :** état, occupation et horodatage des points de charge disponibles dans cet export.
  - **Utilité :** rapprocher localisation et disponibilité des bornes, examiner leur état au moment renseigné.
  - **Attention :** cet export ne constitue pas un historique complet des usages et ne donne pas l’énergie consommée.

- **`bornes_recharge/consolidation_transport_irve_statique_rapport.csv`**
  - **Contenu :** ressources sources, statuts de consolidation et erreurs d’import.
  - **Utilité :** évaluer la qualité et les limites de couverture du fichier statique ; pas mesurer l’activité des bornes.

## Réseau électrique

- **`reseau/poste-electrique.csv`**
  - **Contenu :** localisation des postes et rattachements aux communes, IRIS, intercommunalités, départements et régions.
  - **Utilité :** cartographier les postes, les compter par territoire et étudier leur proximité avec les bornes.
  - **Attention :** aucun historique annuel ni capacité électrique exploitable dans les colonnes présentes. La proximité ne prouve pas le raccordement à un poste.

- **`reseau/donnees-relatives-aux-lignes-et-aux-postes.csv`**
  - **Contenu :** longueurs de lignes HTA/BT, types de lignes et nombre de postes, par année, département, région et ensemble Enedis.
  - **Utilité :** décrire l’infrastructure et son évolution, puis comparer les territoires à ces échelles.
  - **Attention :** ce sont des statistiques agrégées, pas les tracés des lignes ni leur capacité disponible.

## Courbes de charge

- **`courbes_de_charge/RES2-6-9.csv`**
  - **Contenu :** séries à la demi-heure pour 500 identifiants ; colonnes `ID`, `horodate`, `valeur`.
  - **Utilité :** étudier les variations quotidiennes et saisonnières du groupe, construire des profils types.

- **`courbes_de_charge/RES2-9-12.csv`**
  - **Contenu :** même structure pour un second groupe de 500 identifiants.
  - **Utilité :** construire les profils de ce groupe et les comparer au premier.

Les fichiers couvrent novembre 2023 à octobre 2024. Confirmer l’unité de `valeur`, la définition des groupes et leur représentativité avant extrapolation. Aucun code commune ni région n’est présent.

## Quelles données coupler, et pourquoi ?

### Couplages possibles

- **Consommation + puissance solaire communale** : code commune + période annuelle alignée. Base commune aux deux prévisions ; permet de comparer croissance des besoins et du parc solaire.
- **Consommation + IRVE statique** : agréger les points de charge par commune, puis joindre le code commune. Ajoute un indicateur d’équipement en recharge, pas une mesure de consommation des véhicules.
- **Consommation ou solaire + postes** : compter les postes par commune, puis joindre le code commune. Apporte un indicateur de présence du réseau, pas de capacité disponible.
- **IRVE statique + dynamique** : identifiant du point de charge. Relie emplacement et état ; résoudre les répétitions et les horodatages avant jointure.
- **IRVE statique + rapport de consolidation** : identifiants de ressource et de dataset source. Relie les observations à leur provenance et à ses problèmes de qualité.
- **Bornes + postes** : coordonnées, après vérification des systèmes de référence. Permet une analyse de proximité géographique.
- **Consommation + statistiques réseau** : agréger la consommation par département ou région et année. Permet de comparer besoins électriques et infrastructure à la même échelle.
- **Solaire régional + production solaire régionale** : code région, filière solaire et périodes compatibles. Rapproche taille du parc et énergie injectée ; tenir compte des changements de puissance pendant la période.
- **Consommation + production régionale** : agréger la consommation par région et la production sur les mêmes années complètes, puis convertir Wh et MWh. Permet une comparaison annuelle, pas un bilan horaire communal.
- **Les deux fichiers RES2** : concaténer en conservant le groupe d’origine et vérifier les identifiants. Permet de comparer les profils sans perdre leur provenance.

### Couplages à éviter ou à encadrer

- **Courbes RES2 + communes ou régions** : pas de correspondance géographique disponible. Un même horodatage ne suffit pas à relier les séries.
- **Consommation annuelle + production à la demi-heure** : pas de jointure directe. Une désagrégation horaire nécessite des profils et des hypothèses explicites.
- **Production régionale + solaire communal** : on peut rattacher un contexte régional aux communes ; on ne peut pas en déduire une production communale mesurée.
- **Les quatre échelles solaires entre elles** : elles décrivent le même parc à des niveaux différents ; ne pas les additionner. Elles peuvent servir à comparer les agrégations.
- **MW installés + MWh consommés** : pas de soustraction directe. Il faut une estimation de production sur une période commune.
- **IRVE ou postes actuels + années anciennes** : ne pas supposer que les équipements existaient déjà. Un historique ou des dates de mise en service fiables sont nécessaires ; éviter d’introduire des informations futures dans l’entraînement.
- **Équipements + consommation + production** : ces données permettent des indicateurs de pression potentielle, pas une preuve de saturation. Capacités, raccordements et flux détaillés manquent.

Avant toute jointure : codes géographiques harmonisés, mêmes périodes et périmètres, unités compatibles, doublons maîtrisés. Une ligne source absente ou confidentielle ne devient pas automatiquement un zéro.
