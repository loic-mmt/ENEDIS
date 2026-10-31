# Télécharger la production régionale par API

Le script `scripts/download_production_regionale.py` utilise l’API Data Fair d’Enedis, sans dépendance Python externe. Il fonctionne sous macOS et Linux avec Python 3.10 ou plus récent.

Depuis la racine du projet :

```bash
python3 scripts/download_production_regionale.py
```

Pour commencer par deux pages :

```bash
python3 scripts/download_production_regionale.py --max-pages 2
```

Relancer ensuite sans `--max-pages` pour poursuivre dans le même dossier. `Ctrl+C` interrompt le téléchargement ; la même commande permet de reprendre. Garder la même taille de page lors de la reprise.

## Stockage et suivi

Les fichiers sont placés dans `data/raw/production_regionale/`, déjà couvert par la règle Git qui ignore `data/` :

- `metadata.json` conserve le schéma, le total et les métadonnées initiales.
- `page-000001.json.gz`, etc. contiennent les pages compressées, sans conversion des valeurs source. Chaque fichier contient `request_url` et `response` ; les lignes se trouvent dans `response.results`.
- `checkpoint.json` conserve le curseur suivant, le nombre de lignes enregistrées et le statut `complete`.

Le script conserve en mémoire une page à la fois. Par défaut, une page contient au plus 1 000 lignes ; le jeu annonçait 34 089 984 lignes lors du test du 16 octobre 2026. Le total effectif est lu dans les métadonnées à chaque nouveau téléchargement.

Chaque lot est écrit avant la mise à jour du suivi. Si l’écriture du suivi est interrompue, la reprise récupère le lot déjà enregistré. Ne pas modifier ou supprimer les pages ni le fichier de suivi pendant un téléchargement. Un verrou empêche deux instances du script de travailler simultanément dans le même dossier.

Les erreurs réseau temporaires et les réponses HTTP 408, 429, 500, 502, 503 et 504 sont retentées avec attente progressive. Le script s’arrête après épuisement des tentatives et conserve les lots acquis. Une mise à jour détectée du jeu de données bloque la validation ou la reprise : utiliser alors un nouveau dossier avec `--output` pour éviter de mélanger des versions.

Le statut `complete: true` est écrit après vérification du total téléchargé et des métadonnées de version. Ce contrôle ne remplace pas un audit des doublons entre pages, des dates, des valeurs manquantes ou de la qualité métier. Les identifiants sont contrôlés à l’intérieur de chaque page.

## Options

```bash
python3 scripts/download_production_regionale.py --help
```

`--output` change le dossier de destination ; `--timeout`, `--retries` et `--delay` règlent les accès réseau. Le délai par défaut est de 0,2 seconde entre pages. Le téléchargement complet peut représenter plusieurs heures et de nombreux fichiers ; les deux pages testées ne permettent pas de garantir sa durée ni sa taille finale.

## Lire une page

```python
import gzip
import json

with gzip.open("data/raw/production_regionale/page-000001.json.gz", "rt", encoding="utf-8") as stream:
    rows = json.load(stream)["response"]["results"]
```

Pour l’analyse, parcourir les pages successivement plutôt que charger tout le jeu en mémoire.

Après le téléchargement complet, le [guide Parquet](parquet-production-regionale.md) décrit la conversion par lots vers un dataset partitionné par année dans `data/processed/production_regionale/`.

Sources : [documentation du jeu](https://opendata.enedis.fr/datasets/prod-region/api-doc), [métadonnées API](https://opendata.enedis.fr/data-fair/api/v1/datasets/prod-region), [première page](https://opendata.enedis.fr/data-fair/api/v1/datasets/prod-region/lines?size=1000).
