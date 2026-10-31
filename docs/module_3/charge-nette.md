# Module 3 : charge nette régionale

Script : `scripts/module3/charge_nette.py`. Premier test sur la région 93 (PACA).

## Objectif

Mettre en évidence le décalage entre la production solaire et la consommation :

```
charge nette(h) = consommation(h) - production solaire(h)
```

Une charge nette négative à midi signale un excédent de production solaire. Une montée rapide en soirée signale une rampe que le réseau doit absorber quand le solaire s'éteint. Ces deux grandeurs alimenteront l'indicateur de pression.

## Données

- Courbes de charge résidentielles `RES2-6-9.csv` (500 clients, pas de 30 min).
- Consommation résidentielle annuelle 2024 de la région (catégorie `RES` du CSV de consommation, sommée par région).
- Production solaire régionale (`F5 : Solaire`, `P0 : Total toutes puissances`), convertie en heure française.

Deux périodes types : été 2024 (juin à août) et hiver 2023-24 (décembre à février).

## Méthode

On connaît la consommation horaire de 500 clients, pas celle d'une région. On suppose que la région se comporte comme N « clients moyens équivalents », choisi pour retrouver sa consommation annuelle résidentielle :

```
N = E_RES(région, 2024) / (moyenne annuelle de valeur x 8760)
C(h) = N x profil moyen du client à l'heure h x 0,5
```

L'unité de `valeur` s'annule dans ce calcul : elle n'influence pas la forme du résultat, seulement la validité de l'unité affichée.

## Résultats (PACA)

Valeurs lues sur le graphique : ce sont des ordres de grandeur.

**Été 2024**
- La charge nette devient négative d'environ 9 h 30 à 17 h, avec un minimum d'environ -120 MWh par demi-heure vers 10 h 30 - 11 h.
- Rampe du soir : de 17 h à 21 h, la charge nette passe d'environ -40 à plus de 500 MWh par demi-heure.
- La forme est celle d'une courbe en canard (*duck curve*), phénomène connu dans les systèmes à fort solaire.

**Hiver 2023-24**
- La charge nette ne passe jamais sous zéro (minimum d'environ 650 vers 13 h 30).
- Le pic du soir (environ 1 370 vers 19 h) reste intact.

**Cohérence** : le pic solaire d'été 2024 (environ 610) est inférieur à celui de 2025 (704), ce qui correspond à la croissance du parc installé.

## Limites

- **Périmètres différents** : la consommation est uniquement résidentielle, alors que le solaire injecté inclut les grandes centrales. Le creux négatif de midi est donc exagéré. Ce n'est pas une prévision de flux inverse sur le réseau.
- **Extrapolation** : 500 clients pour représenter une région.
- **Moyennes sur trois mois** : elles lissent les journées extrêmes, pourtant les plus importantes pour le réseau.
- **Un seul fichier** de courbes de charge et une seule région testée.
- **Autoconsommation** absente du solaire injecté.

Correction envisagée : comparer le solaire à la consommation totale de la région, ou restreindre le solaire aux petites puissances (plages `P1` à `P3`), plus proches du périmètre résidentiel. À vérifier sur les données.

## Indicateurs proposés

À partir de la charge nette moyenne L(h) d'une région :

- **Creux de midi** = minimum de L(h)
- **Rampe du soir** = maximum de L(h + Δ) - L(h), calculé sur la fin d'après-midi et la soirée (Δ = une heure, par exemple)

Calculés pour les 12 régions, ils donneront un premier classement de pression potentielle, à comparer au classement du solaire installé.

L'indicateur final sert à prioriser les analyses territoriales. Il ne mesure pas la saturation réelle du réseau.

## Prochaines étapes

1. Confirmer l'unité de `valeur`.
2. Corriger le périmètre (consommation totale ou solaire de petite puissance).
3. Étendre le calcul aux 12 régions et en extraire creux et rampe.
4. Journées types plus fines (jours ouvrés, week-end, journées extrêmes) et incertitude.
5. Scénarios 2030 appliqués à la charge nette.
