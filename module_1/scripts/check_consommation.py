"""Contrôles sans correction, avec recherche des doublons entre tous les lots.

Les numéros désignent les enregistrements CSV : en-tête = 1, première donnée = 2.
Les lignes physiques peuvent différer si un champ contient un retour à la ligne.
"""
from pathlib import Path
import json
import sqlite3
import tempfile
import zlib

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/raw/consommation/consommation-electrique-par-secteur-dactivite-commune.csv"
OUTPUT = ROOT / "data/processed/rapports"
KEY = ["Code Commune", "Année", "CODE CATEGORIE CONSOMMATION", "CODE GRAND SECTEUR", "CODE SECTEUR NAF2"]


def main(source=SOURCE, output=OUTPUT, chunksize=100_000):
    output.mkdir(parents=True, exist_ok=True)
    checks = {}
    total = 0

    def record(name, mask, values, numbers, explanation):
        item = checks.setdefault(name, {"count": 0, "examples": [], "explanation": explanation})
        item["count"] += int(mask.sum())
        for idx in mask[mask].index:
            if len(item["examples"]) >= 5:
                break
            item["examples"].append({"enregistrement_csv": int(numbers.loc[idx]), "valeur": str(values.loc[idx])})

    with tempfile.TemporaryDirectory(prefix="enedis_controles_") as tmp:
        with sqlite3.connect(Path(tmp) / "doublons.sqlite") as db:
            db.execute("CREATE TABLE lignes (numero INTEGER, cle TEXT, contenu BLOB)")
            for chunk in pd.read_csv(source, dtype="string", keep_default_na=False,
                                     encoding="utf-8-sig", chunksize=chunksize):
                values = chunk.apply(lambda col: col.str.strip())
                numbers = pd.Series(range(total + 2, total + 2 + len(chunk)), index=chunk.index)
                year = pd.to_numeric(values["Année"], errors="coerce")
                record("Année absente ou invalide", ~values["Année"].str.fullmatch(r"\d{4}") | ~year.between(2011, 2025),
                       values["Année"], numbers, "Année entière attendue entre 2011 et 2025.")
                code = values["Code Commune"]
                record("Format du code commune à vérifier", ~code.str.fullmatch(r"(?:\d{5}|2[AB]\d{3})"), code, numbers,
                       "Format attendu : 5 chiffres ou code corse 2A/2B suivi de 3 chiffres. Ne valide pas l'existence dans un référentiel.")
                numeric_columns = [col for col in chunk.columns if "conso" in col.lower() or col == "nb_sites"]
                # Exclure la colonne de catégorie, qui contient le mot consommation.
                numeric_columns = [col for col in numeric_columns if col != "CODE CATEGORIE CONSOMMATION"]
                for col in numeric_columns:
                    raw = values[col]
                    present = raw.ne("")
                    numeric = pd.to_numeric(raw, errors="coerce")
                    finite = pd.Series(np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan)), index=chunk.index)
                    record(f"{col} : valeur non numérique ou non finie", present & ~finite, raw, numbers,
                           "Cellules vides exclues ; une valeur présente doit être un nombre fini.")
                    record(f"{col} : valeur négative", present & finite & numeric.lt(0).fillna(False), raw, numbers,
                           "Valeur à examiner, sans correction automatique.")
                    if col == "nb_sites":
                        record("Nombre de sites non entier", present & finite & numeric.mod(1).ne(0).fillna(False), raw, numbers,
                               "Un nombre de sites renseigné doit être entier.")
                # Le contenu complet est compressé sans perte, pas remplacé par une empreinte.
                # La clé utilise les textes débarrassés des espaces de bord ; les blancs NAF2 restent distincts des codes.
                keys = values[KEY].itertuples(index=False, name=None)
                rows = chunk.itertuples(index=False, name=None)
                db.executemany("INSERT INTO lignes VALUES (?, ?, ?)", (
                    (int(number), json.dumps(key, ensure_ascii=False),
                     zlib.compress(json.dumps(row, ensure_ascii=False).encode("utf-8"), level=1))
                    for number, key, row in zip(numbers, keys, rows)
                ))
                db.commit()
                total += len(chunk)
                print(f"{total:,} lignes contrôlées…", flush=True)
            if not total:
                raise ValueError("Le fichier ne contient aucune observation.")
            for column, name, explanation in [
                ("contenu", "Lignes entièrement identiques", "Même contenu dans toutes les colonnes, espaces inclus. Aucune suppression effectuée."),
                ("cle", "Clé candidate répétée", "Même commune, année, catégorie, grand secteur et NAF2 après retrait des espaces de bord. Une répétition n'est pas automatiquement une erreur."),
            ]:
                print(f"Recherche : {name}…", flush=True)
                # Les noms de colonnes sont les constantes internes ci-dessus.
                db.execute(f"CREATE INDEX index_{column} ON lignes ({column})")
                query = f"SELECT COUNT(*), MIN(numero) FROM lignes GROUP BY {column} HAVING COUNT(*) > 1"
                groups = involved = extra = 0
                examples = []
                for count, first in db.execute(query):
                    groups += 1
                    involved += count
                    extra += count - 1
                    if len(examples) < 5:
                        examples.append({"premier_enregistrement_csv": first, "nombre_occurrences": count})
                checks[name] = {"count": involved, "examples": examples,
                                "explanation": explanation, "groups": groups, "extra": extra}
    report = []
    for name, item in checks.items():
        report.append({
            "Controle effectue": name,
            "Resultat": "À examiner" if item["count"] else "Aucune anomalie détectée",
            "Nombre de lignes concernees": item["count"],
            "Pourcentage des lignes du fichier": round(item["count"] / total * 100, 4),
            "Nombre de groupes repetes": item.get("groups", ""),
            "Nombre de repetitions apres la premiere occurrence": item.get("extra", ""),
            "Explication du controle": item["explanation"],
            "Exemples (5 maximum)": json.dumps(item["examples"], ensure_ascii=False),
        })
    destination = output / "consommation_verification_formats_et_doublons.csv"
    pd.DataFrame(report).to_csv(destination, index=False, encoding="utf-8-sig")
    print(f"Rapport enregistré : {destination}", flush=True)
    return pd.DataFrame(report)


if __name__ == "__main__":
    main()
