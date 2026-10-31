# Analyser les distributions

Une commande par cible, depuis la racine du dépôt :

```bash
.venv/bin/python scripts/analyse_distributions.py pv --region 53
.venv/bin/python scripts/analyse_distributions.py consommation --region 53
.venv/bin/python scripts/analyse_distributions.py production --region 53
```

`53` est la région par défaut. Dépendances : `requirements.txt`, dont `matplotlib` pour les graphiques.

## Sorties

- Terminal : effectifs, exclusions, quantiles, dispersion et asymétrie ; couverture pour la production.
- CSV : statistiques détaillées et cinq valeurs les plus basses/hautes par groupe avec leurs identifiants. Un petit groupe peut apparaître dans les deux listes d'extrêmes.
- PNG : histogrammes linéaires et logarithmiques ; comparaison annuelle des échantillons ; profils mois/heure et couverture pour la production.

Dossier : `data/processed/rapports/distributions/region_53/<analyse>/<période>/`.
Les fichiers de même nom sont remplacés lors d'une nouvelle exécution. Les données brutes restent inchangées.

Options communes :

```bash
# Période plus courte, histogrammes à 30 classes
.venv/bin/python scripts/analyse_distributions.py pv --region 53 --start-year 2020 --end-year 2025 --bins 30

# Statistiques terminal et CSV, sans graphiques
.venv/bin/python scripts/analyse_distributions.py production --region 53 --no-plots
```

`--data-dir` désigne la racine des sources, `--output-dir` la racine des rapports.
Par défaut : 2011–2025 pour le PV et la consommation ; tous les mois observés pour la production.
Une borne annuelle explicite en production inclut les mois absents jusqu'au début/à la fin de l'année demandée.

## Ce qui est analysé

| Cible | Observation et unité | Comparaison |
| --- | --- | --- |
| PV | Une commune/année source, photovoltaïque uniquement, en MW | Toutes les valeurs disponibles puis mêmes codes valides sur chaque année demandée |
| Consommation | Une ligne publiée commune/catégorie/grand secteur/NAF/année, en MWh | Par année et catégorie ; échantillon commun conservant exactement les mêmes clés sectorielles |
| Production | Une demi-heure solaire F5/P0 de la région, Wh convertis en MWh | Distributions par mois et heure locale ; calendrier attendu en Europe/Paris |

Le PV est rattaché à la région par les départements trouvés dans le fichier de consommation. Les communes PV absentes de ce fichier restent incluses si leur département est identifié.

## Résultats

Résultats pour la Bretagne (`53`). PV et consommation : 2011–2025. Production : juillet 2023 à juin 2026.

### PV communal

- **Hausse nette, plus rapide sur les dernières années.** Sur les 1 045 codes présents chaque année, la puissance médiane passe de **0,198 à 0,585 MW**. La hausse reste donc visible à échantillon commun.
- **Quelques communes ont un parc beaucoup plus important.** En 2025, sur tous les codes disponibles : médiane **0,548 MW**, moyenne **0,913 MW**, maximum **14,33 MW**. La distribution s'étire vers les grandes valeurs ; celles-ci ne sont pas automatiquement des erreurs.
- **Pour les features :** tester les valeurs passées et la croissance récente. Une transformation logarithmique est une piste à comparer sur la validation temporelle.

### Consommation

- **RES offre l'historique le plus comparable.** Sur 1 095 codes communs aux 15 années, la médiane passe de **3 334 à 3 511 MWh**, avec des fluctuations : pas de croissance régulière.
- **ENT et PRO présentent une rupture en 2018** du nombre et du détail des lignes publiées. Aucune clé sectorielle n'est utilisable sur les 15 années pour ces deux catégories. Le changement de distribution ne suffit pas à conclure à une évolution réelle de la consommation.
- **Les manques restent importants dans PRO : 31 % des lignes en 2025.** Dans les trois catégories, quelques grandes valeurs tirent aussi la moyenne vers le haut. Les seules valeurs renseignées peuvent donner une image biaisée.
- **Pour la suite :** RES permet une première sous-analyse. La consommation totale reste la cible principale ; ses distributions communales attendent la validation des catégories à additionner avec le module 1.

### Production solaire

- **Cycles journalier et saisonnier marqués.** Environ **25 % des valeurs connues sont égales à zéro**, concentrées la nuit. Le pic moyen se situe vers **13 h, heure française** ; le profil est plus large et plus élevé en été.
- **Le niveau augmente au fil des années.** Ces distributions seules ne permettent pas de séparer les effets du développement du parc et de la météo.
- **Couverture élevée mais incomplète : 51 786 demi-heures utilisables sur 52 608, soit 98,4 %.** Les 822 autres ont une énergie manquante. Aucun des 36 mois n'est entièrement renseigné : les sommes connues restent partielles.
- **Pour les features mensuelles :** le mois, les valeurs passées et les retards saisonniers sont des pistes. Les cibles mensuelles complètes attendent le traitement des manques ; l'historique ne couvre que trois ans.

Analyses provisoires à rejouer après préparation du module 1. Sens des dates PV, codes géographiques et périmètres restent à confirmer : [bilan de couverture](couverture-bretagne.md).
