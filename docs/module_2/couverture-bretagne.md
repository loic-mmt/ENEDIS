# Couverture des données — Bretagne

Diagnostic des fichiers bruts, sans nettoyage ni imputation. Consommation et PV : 2011–2025. Production solaire : juillet 2023 à juin 2026.

## Conclusion

**La Bretagne (53) sélectionnée région pilote suite aux sorties `scripts/coverage_region_pilote.py`.**

| Source | Résultat | Conséquence |
| --- | --- | --- |
| Comparaison des 12 régions | Bretagne première selon le score de disponibilité des trois sources : 94,0 % | Choix adapté pour commencer l'exploration ; ce score ne mesure pas la quantité d'électricité connue |
| PV communal | 1 114 codes observés ; 1 045 présents sur les 15 années ; aucun doublon, trou interne ou valeur invalide dans la fenêtre | Distribution des puissances publiées analysable dès maintenant |
| Consommation + PV | 33 codes avec PV utilisable et toutes les mesures de consommation publiées renseignées sur les 15 années | Critère très strict ; chaque cible doit conserver son propre échantillon et ses périodes disponibles |
| Production solaire régionale | 98,4 % des demi-heures attendues ont une énergie utilisable ; 0 mois entièrement renseigné sur 36 | Les sommes des valeurs connues restent des totaux partiels |

**33 ne signifie pas que seules 33 communes sont exploitables.** Ce nombre exige une disponibilité simultanée des deux sources sur toute la fenêtre.

| Historique demandé | PV utilisable | PV + consommation renseignée* |
| --- | ---: | ---: |
| Au moins 10 années, pas nécessairement consécutives | 1 067 codes | 357 codes |
| Au moins 10 années consécutives | 1 067 codes | 137 codes |
| Les 15 années | 1 045 codes | 33 codes |

*Consommation renseignée : toutes les mesures publiées pour le code et l'année sont numériques, finies et non négatives. Cela ne prouve pas un total sectoriel exhaustif. Les rapprochements reposent sur les codes et années affichés, avant validation de leur équivalence.*

## Points à confirmer avec le module 1

- Sens exact de `date_mesure` pour le PV ; aucun décalage d'année appliqué ici.
- Millésimes des codes communaux, fusions et changements de périmètre.
- Catégories de consommation à agréger, sans doubles comptes ni totaux partiels présentés comme complets.
- Compatibilité du périmètre des gestionnaires entre parc PV et production Enedis.
- Statut des énergies absentes en production et éventuelles estimations, distinguées des observations.


## Sorties des scripts

Commandes depuis la racine du dépôt. Résumés avec les options par défaut ; exemples communaux limités à dix.

```bash
.venv/bin/python scripts/coverage_region_pilote.py
.venv/bin/python scripts/coverage_pv_communal.py --region 53
```

<details>
<summary>Comparaison des 12 régions et détail Bretagne</summary>

```text
COUVERTURE DES 12 RÉGIONS — fenêtre C/PV : 2011–2025
Production : 2023-07 à 2026-06 (36 mois calendaires attendus).
C : mesures utilisables / lignes publiées, pondéré par années présentes.
PV : années source avec une seule valeur PV utilisable / années demandées.
P : demi-heures uniques, non ambiguës et renseignées / demi-heures attendues.
Utilisable = numérique, finie, non négative ; un zéro explicite est conservé.
Score = minimum de C, PV, P ; départage par leur moyenne, puis historique communal.

Région                              C %  Ans C   PV %    P %  Mois P complets   Communes ≥10 ans*  Score %
53 Bretagne                        94.0     15  100.0   98.4             0/36            389/1270     94.0
11 Île-de-France                   92.5     15  100.0   94.7             1/36            187/1224     92.5
52 Pays de la Loire                94.2     15  100.0   92.1             0/36            435/1490     92.1
93 Provence-Alpes-Côte d'Azur      92.0     15  100.0   97.0             0/36             219/955     92.0
84 Auvergne-Rhône-Alpes            90.2     15  100.0   98.4             0/36            742/4067     90.2
24 Centre-Val de Loire             90.0     15  100.0   95.6             0/36            290/1666     90.0
75 Nouvelle-Aquitaine              88.5     15  100.0   96.7             0/36            619/3943     88.5
28 Normandie                       87.6     15  100.0   94.1             2/36            492/3222     87.6
32 Hauts-de-France                 86.9     15  100.0   94.6             1/36            510/3290     86.9
76 Occitanie                       85.4     15  100.0   94.0             0/36            535/4465     85.4
27 Bourgogne-Franche-Comté         84.0     15  100.0   96.7             0/36            461/3691     84.0
44 Grand Est                       83.8     15  100.0   98.5             0/36            500/4529     83.8

* Années où toutes les mesures publiées de la commune sont utilisables.
Cela ne prouve ni l'exhaustivité sectorielle ni la stabilité des périmètres communaux.

RÉGION PILOTE SUGGÉRÉE (provisoire) : 53 — Bretagne
ATTENTION : aucun mois de production entièrement renseigné pour cette région.
Les sommes connues ne sont pas encore des cibles mensuelles complètes ; voir module 1.
La sélection compare la disponibilité, pas la quantité d'électricité manquante.
Les dates PV sont lues sans décalage : leur sens temporel reste à confirmer.
Le périmètre des gestionnaires du parc PV reste à rapprocher de celui d'Enedis.
Aucune imputation ni correction. Les cellules absentes et invalides restent indisponibles.
Diagnostic C : 3,763,258 lignes lues ; 0 clés absentes ou années invalides ; 0 lignes hors fenêtre/régions.
Diagnostic PV : 716 lignes photovoltaïques ; 0 dates invalides ; 536 lignes hors fenêtre/régions.
Diagnostic P : 631,296 lignes F5/P0 ; 0 dates invalides ou hors grille demi-horaire ; 0 lignes hors régions.

DÉTAIL — Bretagne (53)
Année**   Lignes C connues   Groupes C renseignés*  Lignes RES connues   PV source
2011             7578/7620               1249/1270           1249/1270          OK
2012             7566/7620               1243/1270           1243/1270          OK
2013             7552/7620               1236/1270           1236/1270          OK
2014             7546/7620               1233/1270           1233/1270          OK
2015             7510/7620               1215/1270           1215/1270          OK
2016             7280/7482               1146/1247           1146/1247          OK
2017             7342/7380               1199/1230           1213/1230          OK
2018           14245/15205                544/1232           1232/1232          OK
2019           14173/15143                529/1208           1208/1208          OK
2020           13673/14967                295/1208           1208/1208          OK
2021           13860/15165                288/1208           1208/1208          OK
2022           13887/15231                260/1207           1207/1207          OK
2023           13969/15337                260/1207           1207/1207          OK
2024           13949/15306                257/1206           1206/1206          OK
2025           14065/15414                241/1202           1202/1202          OK
** Année C et année affichée dans la source PV ; équivalence non validée.

Mois local    Créneaux présents   Énergies utilisables   Répétitions
2023-07               1488/1488              1361/1488             0
2023-08               1488/1488              1465/1488             0
2023-09               1440/1440              1417/1440             0
2023-10               1490/1490              1479/1490             0
2023-11               1440/1440              1411/1440             0
2023-12               1488/1488              1482/1488             0
2024-01               1488/1488              1449/1488             0
2024-02               1392/1392              1364/1392             0
2024-03               1486/1486              1472/1486             0
2024-04               1440/1440              1433/1440             0
2024-05               1488/1488              1480/1488             0
2024-06               1440/1440              1435/1440             0
2024-07               1488/1488              1482/1488             0
2024-08               1488/1488              1481/1488             0
2024-09               1440/1440              1432/1440             0
2024-10               1490/1490              1464/1490             0
2024-11               1440/1440              1418/1440             0
2024-12               1488/1488              1464/1488             0
2025-01               1488/1488              1434/1488             0
2025-02               1344/1344              1276/1344             0
2025-03               1486/1486              1465/1486             0
2025-04               1440/1440              1433/1440             0
2025-05               1488/1488              1480/1488             0
2025-06               1440/1440              1429/1440             0
2025-07               1488/1488              1478/1488             0
2025-08               1488/1488              1469/1488             0
2025-09               1440/1440              1419/1440             0
2025-10               1490/1490              1463/1490             0
2025-11               1440/1440              1431/1440             0
2025-12               1488/1488              1479/1488             0
2026-01               1488/1488              1483/1488             0
2026-02               1344/1344              1332/1344             0
2026-03               1486/1486              1460/1486             0
2026-04               1440/1440              1412/1440             0
2026-05               1488/1488              1441/1488             0
2026-06               1440/1440              1413/1440             0

Suite : valider la région et ses périodes avec le module 1 avant les modèles.
```

</details>

<details>
<summary>Couverture du PV communal breton et recoupement avec la consommation</summary>

```text
COUVERTURE PV COMMUNAL — Bretagne (53) — 2011–2025
Départements issus de la consommation : 22, 29, 35, 56.
PV rattaché par préfixe du code commune ; communes absentes de la consommation incluses.
PV utilisable = une seule ligne commune/année, valeur numérique, finie et non négative.
C renseignée* = toutes les mesures publiées de la commune/année sont renseignées et valides.
Un zéro explicite reste valide ; aucun manque remplacé, aucun doublon supprimé.

Codes communaux observés dans la fenêtre : PV 1114, consommation 1270, dans les deux (au moins une année chacun) 1114.
Ces effectifs ne constituent pas un référentiel exhaustif des communes de la région.

Année   PV prés.  PV utilis.  Doubl. PV   C prés.  C renseig.*  C/PV prés.  C/PV renseig.*
2011        1045        1045          0      1270         1249        1045            1030
2012        1057        1057          0      1270         1243        1057            1036
2013        1062        1062          0      1270         1236        1062            1034
2014        1065        1065          0      1270         1233        1065            1034
2015        1066        1066          0      1270         1215        1066            1017
2016        1067        1067          0      1247         1146        1065             972
2017        1067        1067          0      1230         1199        1065            1039
2018        1069        1069          0      1232          544        1069             530
2019        1069        1069          0      1208          529        1069             519
2020        1072        1072          0      1208          295        1071             271
2021        1077        1077          0      1208          288        1075             261
2022        1079        1079          0      1207          260        1077             233
2023        1088        1088          0      1207          260        1086             238
2024        1102        1102          0      1206          257        1100             240
2025        1114        1114          0      1202          241        1112             228
C/PV : même code ET même année affichée dans les deux sources.
Doubl. PV : nombre de clés commune/année répétées, pas nombre de lignes supplémentaires.

HISTORIQUES — nombre de communes par nombre d'années dans la fenêtre
Nb années    PV présentes   PV utilisables   C/PV renseignées*
0                     156              156                 191
1                      12               12                   8
2                      14               14                   6
3                       9                9                   1
4                       2                2                   6
5                       5                5                   9
6                       3                3                  16
7                       0                0                 363
8                       2                2                 101
9                       0                0                 212
10                      1                1                  99
11                      1                1                  81
12                      3                3                  57
13                      5                5                  41
14                     12               12                  46
15                   1045             1045                  33
PV utilisable : ≥ 10 ans 1067 communes ; ≥ 10 ans consécutifs 1067 ; fenêtre entière 1045.
C/PV renseignées* : ≥ 10 ans 357 communes ; ≥ 10 ans consécutifs 137 ; fenêtre entière 33.

ABSENCES ET RÉPÉTITIONS — exemples limités
Trou interne = année sans ligne PV entre première et dernière années PV présentes.
Les absences aux extrémités restent distinctes ; aucune absence ne prouve un parc nul.
Codes uniquement dans la consommation : 156
  22006 ; 22007 ; 22016 ; 22023 ; 22024 ; 22027 ; 22037 ; 22038 ; 22039 ; 22040
  … 146 autres ; --details all pour le détail par commune.
Codes uniquement dans le PV : 0
Communes avec trous PV internes : 0
Communes avec valeurs PV absentes ou invalides : 0
Clés PV répétées (0 lignes supplémentaires) : 0

LECTURE C : 3,763,258 lignes parcourues ; 174,730 dans la région ; 0 clés invalides/incohérentes ; 0 lignes hors fenêtre.
LECTURE PV : 384,715 lignes parcourues ; 18,398 lignes photovoltaïques de la région ; 0 dates invalides ; 2,299 lignes hors fenêtre.
PV dans la fenêtre : 16,099 lignes ; 0 valeurs absentes/invalides ; 0 zéros explicites.
Codes PV invalides, toutes régions (non attribuables) : 0 lignes photovoltaïques.

* Toutes les valeurs publiées connues ne prouvent pas un total sectoriel exhaustif.
Dates PV conservées sans décalage ; équivalence avec l'année de consommation à confirmer.
Codes comparés tels que publiés : fusions, changements de code et millésimes non harmonisés.
Rattachement département/région issu du fichier C ; existence officielle des codes non validée.
Diagnostic de disponibilité uniquement ; corrections et complétions relèvent du module 1.
```

</details>

