# Anticiper les pressions potentielles sur le réseau électrique à l’horizon 2030

## Problématique

Comment anticiper les territoires présentant les plus fortes pressions potentielles sur le réseau électrique à l’horizon 2030, à partir des prévisions de développement du photovoltaïque et d’évolution de la consommation ?

Cette question répond à l'enjeu d'Enedis : évaluer les besoins d’adaptation du réseau électrique liés à l’électrification des usages et au développement du photovoltaïque.

Le réseau électrique a historiquement été conçu pour transporter l’électricité depuis de grands sites de production vers les consommateurs. Aujourd’hui, deux transformations se produisent simultanément :

- **La production se décentralise.** De plus en plus de bâtiments produisent de l’électricité grâce au photovoltaïque. Une production locale élevée peut créer des flux inverses, des contraintes de tension et des besoins de renforcement du réseau.
- **La consommation s’électrifie.** Les véhicules électriques, les pompes à chaleur et d’autres nouveaux usages peuvent augmenter les appels de puissance, notamment à certaines heures.

Les besoins électriques deviennent ainsi plus variables dans l’espace et dans le temps. Une commune peut disposer d’une production solaire importante à midi, puis connaître une forte consommation le soir. L’enjeu consiste à anticiper ces décalages pour prioriser les analyses territoriales.

## Objectifs

- **Objectifs scientifiques :** développer un modèle prédictif spatio-temporel, identifier les déterminants des évolutions territoriales, simuler des scénarios d’électrification et quantifier l’incertitude.
- **Objectif technique :** construire une infrastructure de données reproductible et une application de visualisation permettant d’explorer les résultats par territoire.

## Organisation du projet

### Module 1 — Ingénierie des données

Collecter les données historiques, les structurer avec SQL et PostGIS, puis harmoniser les référentiels géographiques.

### Module 2 — Prédiction

Prévoir l’évolution de la consommation électrique et du développement photovoltaïque.

### Module 3 — Modélisation et scénarios

Comprendre les facteurs explicatifs des évolutions territoriales, simuler différents scénarios et estimer les incertitudes associées.

### Livrable commun — Application interactive

L’application réunira une carte, des prévisions, des scénarios à l’horizon 2030, des visualisations et des indicateurs de pression potentielle sur le réseau.

## Infrastructure de données

Le volet d’ingénierie des données et d’architecture de base de données comprend :

- Une base PostgreSQL/PostGIS organisée en tables de communes, de consommation annuelle, de production solaire, d’installations électriques et de données météorologiques.
- Des pipelines ETL automatisés en Python et SQL, avec contrôle de qualité, détection des doublons et gestion des mises à jour.
- Des requêtes spatiales pour relier les communes, les infrastructures électriques et les données solaires.
- Des vues SQL et une API FastAPI pour rendre les données accessibles aux modèles et à l’application.

La principale difficulté technique consiste à harmoniser les codes INSEE et à prendre en compte les changements de périmètre des communes au cours du temps.

## Approche scientifique

### 1. Prédire le développement photovoltaïque

La puissance photovoltaïque installée peut être estimée à partir des données historiques et des caractéristiques territoriales :

$$
\widehat{P}^{PV}_{i,t+h} = f(X_{i,t}, X_{i,t-1}, Z_i)
$$

où $P^{PV}$ désigne la puissance photovoltaïque installée dans le territoire $i$, $h$ l’horizon de prévision, $X$ les variables historiques et $Z_i$ les caractéristiques du territoire.

L’étude comparera plusieurs approches : régression régularisée, modèles de panel, XGBoost et modèles temporels.

### 2. Modéliser les évolutions et simuler des scénarios

Construire des modèles explicatifs de la consommation et du développement photovoltaïque, puis simuler plusieurs scénarios d’adoption des véhicules électriques et des pompes à chaleur.

### 3. Construire un indicateur de pression potentielle

Construire un indicateur composite à partir de la croissance photovoltaïque, de la consommation projetée, des scénarios de pointe et de certaines caractéristiques spatiales du réseau.

Cet indicateur servira à **prioriser les analyses territoriales**. Il ne constituera pas une mesure démontrée de la saturation du réseau.

## Données

| Données | Source et granularité | Intérêt |
| --- | --- | --- |
| [Consommation électrique](https://opendata.enedis.fr/datasets/consommation-electrique-par-secteur-dactivite-commune/) | Enedis, annuelle par commune, 2011–2024 | Étudier les besoins électriques locaux |
| [Puissance photovoltaïque installée](https://www.data.gouv.fr/datasets/puissance-solaire-installee) | ODRE, données communales | Mesurer la progression du solaire |
| [Production électrique par demi-heure](https://opendata.enedis.fr/datasets/prod-region/) | Enedis, régionale, environ 34 millions de lignes | Prédire la production à court terme |
| [Localisation des postes électriques](https://opendata.enedis.fr/datasets/poste-electrique) | Enedis, coordonnées des postes HTA/BT | Analyser la répartition spatiale du réseau |
| [Lignes et postes électriques](https://opendata.enedis.fr/datasets/donnees-relatives-aux-lignes-et-aux-postes) | Enedis, infrastructures du réseau | Construire des indicateurs territoriaux |
| [Bornes de recharge électrique](https://www.data.gouv.fr/datasets/beta-bases-nationales-des-points-de-recharge-pour-vehicules-electriques-en-france-irve) | Base nationale IRVE, localisation et caractéristiques | Intégrer l’électrification des transports |
| [PVGIS](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/api-non-interactive-service_en) | Commission européenne, données solaires horaires et simulations | Modéliser l’influence de l’ensoleillement |
