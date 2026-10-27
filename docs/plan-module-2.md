# Plan du module 2 — Prédiction à l’horizon 2030

## 1. Périmètre

Utiliser exclusivement les données fournies par Open Data University, préparées par le module 1. Aucun jeu de données complémentaire n’est requis.

| Cible | Données utilisées | Sortie |
| --- | --- | --- |
| Consommation électrique | Historique de consommation communale | MWh par commune et année |
| Puissance photovoltaïque installée | Historique du parc solaire | MW par commune et année |
| Production solaire injectée | Séries de `data/raw/production_regionale/` | MWh par région et année, avec décomposition mensuelle si utile |

Commencer sur une région pilote, puis étendre aux territoires couverts. Agréger la consommation et le parc PV à la région pour le module de modélisation.

## 2. Étapes du projet

| Étape | Travail à réaliser | Livrable |
| --- | --- | --- |
| 1. Préparer les entrées | Récupérer les données du module 1 ; vérifier unités, dates, doublons, périmètres et couverture. Pour la production, sélectionner le solaire `F5` et le total des puissances `P0`. | Jeux prêts pour l’apprentissage |
| 2. Analyser les historiques | Étudier tendances, saisonnalité, ruptures et données manquantes. Choisir les territoires et années exploitables. | Diagnostic synthétique |
| 3. Établir les références | Tester la persistance et la tendance linéaire pour les cibles annuelles ; une référence saisonnière pour la production. | Premiers résultats et scores de référence |
| 4. Construire les modèles | Créer les variables historiques et calendaires ; comparer les méthodes proposées ci-dessous. | Modèles candidats |
| 5. Valider | Entraîner sur le passé et tester sur des périodes suivantes. Comparer MAE, RMSE, biais et couverture par cible, région et horizon. | Modèles retenus et erreurs historiques |
| 6. Projeter jusqu’en 2030 | Produire les trajectoires annuelles et vérifier leur cohérence régionale. Expliciter les hypothèses de croissance et de saisonnalité. | Prévisions et hypothèses |
| 7. Livrer | Automatiser les exports et vérifier leur lecture par le module de modélisation sur la région pilote. | Livraison reproductible |

## 3. Méthodes à comparer

- **Consommation :** références simples, puis régression régularisée ou modèle d’arbres utilisant les historiques de plusieurs communes.
- **Parc PV :** tendance récente, puis modèle mutualisé entre communes à partir des niveaux et variations passés.
- **Production solaire :** modèle régional de tendance et de saisonnalité, appris sur les séries fournies. Utiliser les mois et les valeurs passées ; intégrer l’évolution prévue du parc si les périmètres sont compatibles.

Pour la production à l’horizon 2030, la projection suppose une saisonnalité comparable à celle observée. La météo future n’est pas modélisée explicitement. Conserver une méthode simple si les modèles plus complexes n’améliorent pas la validation.

## 4. Livraison au module de modélisation

- Trajectoires : territoire, année, cible, valeur prévue, unité, modèle et statut de qualité.
- Erreurs historiques hors entraînement pour alimenter son Monte-Carlo.
- Hypothèses retenues et couverture des résultats.

Le module de modélisation garde la construction des profils journaliers, les scénarios solaire/VE, la charge nette et les indicateurs de pression. Les scénarios sont définis par rapport à une référence commune pour éviter les doubles comptes.

## 5. Points de vigilance

- Une donnée absente reste distincte d’un zéro ; un total incomplet est signalé.
- Confirmer le sens des dates du parc PV et la comparabilité des territoires avec le module 1. Ne pas utiliser d’informations futures pendant la validation.
- La production couvre trois ans et 12 régions : 2030 reste une projection sous hypothèses, dont la précision à cinq ans ne peut pas être validée directement avec cet historique.

[Plan du module 1](plan-module-1.md)
