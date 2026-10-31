# Plan du module 3 — Modélisation et scénarios à l’horizon 2030

## 1. Périmètre

Expliquer les évolutions régionales de la consommation et du solaire, simuler des scénarios à 2030 et quantifier l’incertitude, pour alimenter l’indicateur de pression potentielle commun avec le module 2. Travail à l’échelle de la **région**.

| Sortie | Données utilisées | Statut |
| --- | --- | --- |
| Profils journaliers solaire par région | `data/raw/production_regionale/` (`F5` et `P0`) | fait, voir `profil-solaire.md` |
| Profils journaliers de consommation | `data/raw/courbes_de_charge/RES2-6-9.csv` | fait, voir `courbes-de-charge.md` |
| Charge nette par région | profils solaire et consommation, consommation annuelle régionale | premier test sur PACA, voir `charge-nette.md` |
| Scénarios solaire et véhicules électriques | trajectoires du module 2, bornes de recharge (`data/raw/bornes_recharge/`) | à faire |
| Incertitude (Monte-Carlo) | erreurs historiques du module 2, hypothèses de scénario | à faire |
| Indicateurs de pression par région | charge nette, scénarios, caractéristiques du réseau (`data/raw/reseau/`) | à faire |

Hors périmètre : les pompes à chaleur. Aucune donnée directe n’existe, et une seule colonne indirecte (taux de chauffage électrique) ne suffit pas à construire un scénario défendable.

## 2. Étapes du projet

| Étape | Travail à réaliser | Livrable |
| --- | --- | --- |
| 1. Préparer les entrées | Vérifier unités, dates, doublons et couverture des données de production, de consommation et des courbes de charge. Confirmer l’unité de la colonne `valeur` des courbes de charge. | Jeux contrôlés (fait pour la production 2025 et `RES2-6-9`) |
| 2. Construire les profils journaliers | Profils moyens par région, saison et heure du jour, en heure française. Étendre aux 12 régions et traiter `RES2-9-12`. | Profils par région |
| 3. Calculer la charge nette | Consommation estimée moins production solaire, par région et par saison. Corriger le périmètre (consommation totale ou solaire de petite puissance). | Charge nette par région |
| 4. Extraire les indicateurs | Creux de midi (minimum de la charge nette) et rampe du soir (montée maximale sur une heure). | Premier classement des régions |
| 5. Expliquer les évolutions | Tableau région × année et modèle explicatif simple (effets fixes), à partir des historiques régionaux. | Facteurs explicatifs |
| 6. Définir les scénarios | Scénarios bas, central et haut pour le solaire et les véhicules électriques, définis par rapport à la référence du module 2. | Scénarios 2030 |
| 7. Quantifier l’incertitude | Monte-Carlo sur les hypothèses, avec les erreurs historiques du module 2. | Intervalles par région |
| 8. Construire l’indicateur de pression | Combiner creux, rampe, scénarios et réseau avec des poids explicites ; tester la sensibilité aux pondérations. | Indicateur et classement |

## 3. Méthodes

- **Profils et charge nette :** moyennes par heure du jour et par saison. La consommation régionale est estimée en supposant que la région se comporte comme N clients moyens équivalents, calé sur sa consommation annuelle résidentielle (voir `charge-nette.md`).
- **Modèle explicatif :** régression avec effets fixes par région, volontairement simple (environ 200 observations au niveau région).
- **Scénarios :** hypothèses de croissance du solaire et d’adoption des véhicules électriques, appliquées au profil de charge nette.
- **Incertitude :** tirage aléatoire des hypothèses dans des fourchettes (Monte-Carlo), pour identifier celles qui pèsent le plus sur le résultat.
- **Indicateur :** normalisation de chaque composante par rangs ou z-scores, puis combinaison pondérée.

## 4. Entrées attendues du module 2

- Trajectoires annuelles à 2030 : région, année, cible, valeur prévue, unité, modèle et statut de qualité.
- Erreurs historiques hors entraînement, pour le Monte-Carlo.
- Hypothèses retenues et couverture des résultats.

Le module 3 garde la construction des profils journaliers, les scénarios solaire/VE, la charge nette et les indicateurs de pression. Les scénarios sont définis par rapport à une référence commune pour éviter les doubles comptes.

## 5. Points de vigilance

- Une donnée absente reste distincte d’un zéro (`NaN`, avec une colonne `conso_manquante`) ; à confirmer avec le module 1.
- L’unité de `valeur` dans les courbes de charge n’est pas confirmée (watts supposés). Elle n’influence pas la forme de la charge nette, seulement l’unité affichée.
- 500 clients ne représentent pas une région : l’extrapolation repose sur une hypothèse.
- La consommation estimée est résidentielle, le solaire injecté inclut les grandes centrales : le creux négatif de midi est exagéré et n’est pas une prévision de flux inverse.
- Les courbes de charge couvrent 11/2023 à 10/2024, le profil solaire de référence porte sur 2025 : on compare des journées types, pas des dates précises.
- La production couvre trois ans et 12 régions : 2030 reste une projection sous hypothèses.
- L’indicateur final sert à prioriser les analyses territoriales. Il ne mesure pas la saturation réelle du réseau.

[Plan du module 1](../../module_1/docs/plan-module-1.md) · [Plan du module 2](../module_2/plan-module-2.md)