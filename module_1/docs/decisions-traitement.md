# Consommation électrique : ce qu’on a trouvé et ce qu’on va faire

## 1. À quoi sert ce document ?

On a analysé **3 763 258 lignes de données, de 2011 à 2025**, pour repérer les cellules vides. Ce document explique les résultats et les choix à faire avant de mettre les données dans la base SQL.

**Pour le moment, on garde toutes les lignes et toutes les colonnes. On ne remplit aucune valeur manquante automatiquement.**

Elle concerne seulement le fichier de consommation ; les autres jeux seront étudiés ensuite.

## 2. Qu’est-ce qu’on a trouvé ?

### Les informations pour relier les données sont présentes

L’année, le code commune, les codes département et région sont renseignés sur toutes les lignes.

C’est utile pour relier les fichiers entre eux. Il faudra quand même vérifier que les codes sont corrects et correspondent à la bonne année.

### Il manque environ 12 consommations sur 100 lignes

La consommation totale est vide sur **446 907 lignes, soit 11,88 %**. Le nombre de sites est absent exactement sur les mêmes lignes.

Une cellule vide ne veut pas dire que la consommation est nulle.

**Exemple :** si une commune a une consommation inconnue, mettre `0` ferait croire qu’elle n’a consommé aucune électricité. On laisse donc la valeur manquante. Dans SQL, on utilisera `NULL`, qui signifie « valeur non renseignée ».

### Les manques ne touchent pas tous les groupes de la même façon

Le fichier utilise les codes de catégorie suivants. Leur définition précise reste à vérifier dans la documentation source.

| Code dans le fichier | Consommations totales manquantes |
| --- | --- |
| `ENT` | 0 % |
| `PRO` | Environ 39 % |
| `RES` | Environ 7 % |

Dans `PRO`, le taux dépend aussi du secteur : il va d’environ 14 % à 72 %.

**Ce que cela change :** supprimer toutes les lignes incomplètes ferait perdre beaucoup plus de données dans certains groupes. On les garde et on indiquera les manques dans les analyses.

### Il y a davantage de manques depuis 2018

| Période | Part des lignes sans consommation totale |
| --- | --- |
| 2011 à 2017 | Environ 4 à 5 % selon l’année |
| 2018 à 2025 | Environ 16 % selon l’année |

Le nombre de lignes change aussi en 2018. Il faut vérifier si la manière de publier les données a changé. **Cela ne signifie pas que la consommation a baissé ou augmenté.**

### Une partie des absences semble liée à la confidentialité

La colonne `Nombre de mailles secretisées` indique des informations liées à la confidentialité. Son fonctionnement exact reste à confirmer dans la documentation.

Parmi les **446 907 lignes sans consommation totale** :

- **383 531** ont un nombre de mailles secretisées supérieur à zéro ;
- **63 376** ont aussi cette information vide.

Cela suggère un lien avec la confidentialité, mais ne prouve pas la cause de chaque absence. Certaines lignes ont d’ailleurs une consommation renseignée malgré un nombre de mailles secretisées positif.

**Notre choix :** garder la colonne de secretisation, laisser les consommations absentes en `NULL` et ne pas essayer de les reconstituer automatiquement.

### Les colonnes très vides peuvent quand même être utiles

Certaines informations ne sont présentes que pour certaines années ou certains groupes.

| Information | Ce qu’on observe | Ce qu’on fait |
| --- | --- | --- |
| Population | Renseignée uniquement sur des lignes résidentielles de 2024 et 2025 | On la conserve pour ces périodes |
| Taux de chauffage électrique | Renseigné uniquement sur des lignes résidentielles de 2024 | On le conserve sans le recopier aux autres années |
| `part_thermosensible` | Présente seulement sur une partie des lignes résidentielles, à partir de 2017 | On la conserve ; elle décrit la sensibilité de la consommation à la température, avec une définition précise à confirmer |
| `CODE SECTEUR NAF2` | Ce détail du secteur d’activité est renseigné seulement sur certaines lignes `ENT`, à partir de 2018 | On garde les codes existants sans en inventer pour les autres lignes |
| Codes PNR et EPT | Souvent vides | On vérifie si ces rattachements territoriaux s’appliquent aux communes concernées |

**Exemple :** une information disponible en 2024 peut servir à une analyse de 2024. On ne suppose pas qu’elle avait la même valeur en 2011.

### Certaines moyennes pourraient être calculées, après vérification

Sur **84 701 lignes**, la consommation moyenne est absente alors que la consommation totale et le nombre de sites sont renseignés.

Un calcul pourrait être possible :

```text
consommation moyenne = consommation totale / nombre de sites
```

Mais il faut d’abord vérifier que le nombre de sites est bien un nombre supérieur à zéro et que cette formule correspond à la définition de la source.

**Notre choix actuel :** ne rien calculer encore. Si on utilise cette formule plus tard, on enregistrera le résultat séparément pour distinguer la moyenne calculée de la moyenne fournie.

## 3. Quelles décisions prend-on maintenant ?

| Situation | Décision |
| --- | --- |
| Cellule vide | La laisser manquante ; utiliser `NULL` dans SQL |
| Valeur explicitement égale à zéro | Garder le zéro |
| Ligne avec des informations manquantes | La conserver : ses autres informations peuvent servir |
| Colonne presque vide | La conserver et préciser les années et groupes où elle est disponible |
| Consommation peut-être masquée pour confidentialité | Ne pas la remplacer automatiquement |
| Information présente seulement sur une année récente | Ne pas la recopier dans le passé |
| Calcul ou estimation réalisé plus tard | Le distinguer de la valeur d’origine |

Quand on additionnera les consommations, il faudra préciser si certaines valeurs manquent. **La somme des valeurs connues peut être un total incomplet.** Il faudra aussi vérifier que les catégories additionnées ne comptent pas plusieurs fois les mêmes consommations.

## 4. Qu’est-ce qu’il reste à faire, dans l’ordre ?

1. **Comprendre les définitions du fichier.** Vérifier ce que signifient les catégories, la secretisation et les niveaux de détail des secteurs dans la documentation source.
2. **Vérifier les valeurs présentes.** Contrôler que les années et les nombres sont lisibles, que les codes commune sont valides et que les nombres de sites sont cohérents.
3. **Chercher les doublons.** Vérifier si une même observation apparaît plusieurs fois. Deux lignes d’une même commune et d’une même année peuvent être normales si elles concernent des secteurs différents.
4. **Examiner les moyennes manquantes.** Vérifier les 84 701 lignes avant de décider si on peut calculer leur moyenne.
5. **Préparer les tables SQL.** Importer les données en conservant leurs valeurs d’origine et les manques, puis créer des tables contrôlées pour les analyses.

**On n’a pas besoin de remplir toutes les cellules pour créer la base.** Le but est de conserver les données et de savoir lesquelles peuvent être utilisées pour chaque analyse.

## 5. Où retrouver les chiffres détaillés ?

Les pourcentages de ce document portent sur des **lignes du fichier**, pas sur la proportion de communes touchées ni sur la quantité d’électricité manquante.

Le script `profile_data.py` compte les cellules vides ou contenant seulement des espaces. Les contrôles complémentaires de formats et de doublons sont décrits dans la section suivante. Les causes supposées des manques restent à confirmer.

| Fichier | À quoi il sert |
| --- | --- |
| [Rapport global](../../data/processed/rapports/consommation_valeurs_manquantes.csv) | Voir le nombre de cellules vides dans chaque colonne |
| [Rapport par année](../../data/processed/rapports/consommation_manques_par_annee.csv) | Voir les différences entre les années |
| [Rapport par catégorie et secteur](../../data/processed/rapports/consommation_manques_par_categorie_secteur.csv) | Repérer les groupes les plus touchés |
| [Rapport des combinaisons](../../data/processed/rapports/consommation_combinaisons_manques.csv) | Voir quelles informations manquent ensemble ; `True` signifie que le champ est vide, `False` qu’il est renseigné |


## 6. Nouveau rapport : vérification des formats et des doublons

Le script [check_consommation.py](../scripts/check_consommation.py) produit le fichier **`consommation_verification_formats_et_doublons.csv`** dans `data/processed/rapports/`.

Pour le lancer depuis le dossier du projet :

```bash
.venv/bin/python module_1/scripts/check_consommation.py
```

Chaque ligne du rapport correspond à un contrôle : année, format du code commune, nombres de consommation, nombre de sites ou doublons. Les cellules vides des mesures sont laissées aux rapports de valeurs manquantes ; elles ne sont pas signalées à nouveau comme des nombres invalides.

| Colonne du rapport | Signification |
| --- | --- |
| `Controle effectue` | Ce qui a été vérifié |
| `Resultat` | Présence ou absence de cas à examiner pour ce contrôle |
| `Nombre de lignes concernees` | Nombre de lignes qui demandent une vérification |
| `Pourcentage des lignes du fichier` | Part de ces lignes dans le fichier complet |
| `Nombre de groupes repetes` | Nombre de groupes contenant plusieurs occurrences, uniquement pour les doublons |
| `Nombre de repetitions apres la premiere occurrence` | Nombre d’occurrences supplémentaires, uniquement pour les doublons |
| `Explication du controle` | Règle appliquée et ses limites |
| `Exemples (5 maximum)` | Valeurs et numéros permettant de retrouver quelques cas |

**Exemple pour les doublons :** une ligne présente trois fois forme un groupe répété, concerne trois lignes et compte deux occurrences supplémentaires. Les doublons sont recherchés dans tout le fichier, même lorsqu’ils se trouvent dans des lots de lecture différents.

Les numéros d’exemple comptent les enregistrements CSV : l’en-tête est le numéro 1 et la première donnée le numéro 2. Ils peuvent différer des lignes affichées par un éditeur si une cellule contient un retour à la ligne.

Une clé répétée signifie que commune, année, catégorie, grand secteur et NAF2 sont identiques après retrait des espaces au début et à la fin. Cela ne suffit pas à décider de supprimer une ligne. Le contrôle du code commune vérifie son format, pas son existence officielle. Aucune correction ou suppression automatique n’est effectuée.

### Résultat du contrôle du 29 octobre 2026

Les **3 763 258 lignes** ont été parcourues. Les **23 contrôles** du rapport n’ont détecté aucun cas à examiner :

- années et formats de code commune conformes aux règles testées ;
- consommations renseignées numériques, finies et non négatives ;
- nombres de sites renseignés entiers et non négatifs ;
- aucune ligne entièrement identique ;
- aucune répétition pour la combinaison commune + année + catégorie + grand secteur + NAF2.

Ces résultats ne suppriment pas les valeurs manquantes déjà recensées et ne valident pas l’existence officielle des codes commune. Ils ne vérifient pas non plus que des totaux et leurs détails peuvent être additionnés sans double compte. Le script ne teste pas encore si une moyenne manquante peut être calculée : il faudra notamment vérifier le dénominateur et la définition de la source.
