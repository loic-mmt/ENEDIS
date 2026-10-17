#!/usr/bin/env python3
"""Download Enedis regional production as resumable, compressed JSON pages.

Python 3.10+, standard library only. Run again with the same output directory
to resume. Each .json.gz preserves the API's results, total and next cursor.
"""

import argparse
import fcntl
import gzip
import json
import os
import random
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


DATASET_URL = "https://opendata.enedis.fr/data-fair/api/v1/datasets/prod-region"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data/raw/production_regionale"


def request_json(url, timeout, retries):
    """Retry transient failures; never silently skip a page."""
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "enedis-research-downloader/1.0",
            })
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            if isinstance(error, HTTPError) and error.code not in (408, 429, 500, 502, 503, 504):
                raise
            if attempt == retries:
                raise
            delay = min(120, 2 ** attempt) + random.uniform(0, 1)
            if isinstance(error, HTTPError):
                retry_after = error.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    delay = max(delay, int(retry_after))
            print(f"Erreur temporaire : {error}. Nouvel essai dans {delay:.1f} s.",
                  file=sys.stderr, flush=True)
            time.sleep(delay)


def atomic_json(path, value, compressed=False):
    """Publish a complete file before advancing the checkpoint."""
    temporary = path.with_name(path.name + ".part")
    with temporary.open("wb") as raw:
        if compressed:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
                stream.write(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        else:
            raw.write(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(temporary, path)


@contextmanager
def exclusive_download(directory):
    # OS releases the lock even after interruption or process termination.
    with (directory / ".download.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Un téléchargement utilise déjà ce dossier.") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def revision(metadata):
    return {key: metadata.get(key) for key in ("id", "dataUpdatedAt", "updatedAt", "count")}


def validate_page(page, state):
    if not isinstance(page, dict) or not isinstance(page.get("results"), list):
        raise ValueError("Réponse API invalide : results absent ou incorrect.")
    # Data Fair omits total on subsequent cursor pages.
    if page.get("total") is not None and page["total"] != state["total"]:
        raise ValueError("Le total a changé : conserver les lots et recommencer dans un autre dossier.")
    results = page["results"]
    if not results:
        raise ValueError("Page vide avant la fin attendue du téléchargement.")
    identifiers = [row.get("_id") for row in results]
    if any(not value for value in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("Identifiants absents ou répétés dans une page.")
    next_url = page.get("next")
    if next_url is not None:
        parsed = urlsplit(next_url)
        if (parsed.scheme != "https" or parsed.netloc != "opendata.enedis.fr"
                or not parsed.path.startswith("/data-fair/api/v1/datasets/")
                or next_url == state["next"]):
            raise ValueError("Curseur de pagination invalide.")
    count = state["downloaded"] + len(results)
    if count > state["total"] or (not next_url and count != state["total"]):
        raise ValueError("Fin de pagination incohérente avec le nombre de lignes attendu.")
    if next_url and count == state["total"]:
        raise ValueError("Curseur supplémentaire malgré un total déjà atteint.")


def download(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / "checkpoint.json"
    with exclusive_download(output):
        metadata = request_json(DATASET_URL, args.timeout, args.retries)
        current_revision = revision(metadata)
        if checkpoint.exists():
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
            if state["revision"] != current_revision:
                raise RuntimeError("Source modifiée depuis le début. Utiliser un nouveau dossier --output.")
            if state["page_size"] != args.page_size:
                raise RuntimeError(f"Reprise : utiliser --page-size {state['page_size']}.")
            expected_files = {f"page-{number:06d}.json.gz" for number in range(1, state["pages"] + 1)}
            missing = expected_files - {path.name for path in output.glob("page-*.json.gz")}
            if missing:
                raise RuntimeError(f"Lots manquants : {sorted(missing)[:3]}. Restaurer avant reprise.")
        else:
            if any(output.glob("page-*.json.gz")):
                raise RuntimeError("Lots présents sans checkpoint. Utiliser un dossier vide.")
            total = metadata.get("count")
            if not isinstance(total, int) or total <= 0:
                raise ValueError("Nombre de lignes invalide dans les métadonnées.")
            state = {
                "dataset": DATASET_URL, "revision": current_revision,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "page_size": args.page_size, "total": total,
                "downloaded": 0, "pages": 0, "complete": False,
                "next": DATASET_URL + "/lines?" + urlencode({"size": args.page_size}),
            }
            atomic_json(output / "metadata.json", metadata)
            atomic_json(checkpoint, state)

        print(f"Dossier : {output}\nReprise : {state['downloaded']:,} / {state['total']:,} lignes.", flush=True)
        pages_this_run = 0
        started = time.monotonic()
        initial_count = state["downloaded"]
        while state["next"] and (args.max_pages is None or pages_this_run < args.max_pages):
            url = state["next"]
            path = output / f"page-{state['pages'] + 1:06d}.json.gz"
            if path.exists():
                # Recover a page committed just before an interrupted checkpoint write.
                with gzip.open(path, "rt", encoding="utf-8") as stream:
                    saved = json.load(stream)
                if saved.get("request_url") != url:
                    raise RuntimeError(f"Lot incompatible avec le checkpoint : {path}")
                page = saved["response"]
                validate_page(page, state)
            else:
                page = request_json(url, args.timeout, args.retries)
                validate_page(page, state)
                atomic_json(path, {"request_url": url, "response": page}, compressed=True)
            state["downloaded"] += len(page["results"])
            state["pages"] += 1
            state["next"] = page.get("next")
            atomic_json(checkpoint, state)
            pages_this_run += 1
            elapsed = max(time.monotonic() - started, 0.001)
            rate = (state["downloaded"] - initial_count) / elapsed
            print(f"Lot {state['pages']:06d} : {state['downloaded']:,}/{state['total']:,} "
                  f"({100 * state['downloaded'] / state['total']:.2f} %) — {rate:.0f} lignes/s", flush=True)
            if state["next"]:
                time.sleep(args.delay)

        if not state["next"]:
            latest = request_json(DATASET_URL, args.timeout, args.retries)
            if revision(latest) != state["revision"]:
                raise RuntimeError("Source modifiée pendant le téléchargement : résultat non validé.")
            state["complete"] = True
            state["completed_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(checkpoint, state)
            print(f"Terminé : {state['downloaded']:,} lignes. Total vérifié, source inchangée.", flush=True)
        else:
            print("Limite de test atteinte. Relancer sans --max-pages pour poursuivre.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--page-size", type=int, default=1000, help="Taille des pages (défaut : 1000, testé sur Enedis).")
    parser.add_argument("--max-pages", type=int, help="Limiter les lots de cette exécution pour un test.")
    parser.add_argument("--timeout", type=float, default=60, help="Timeout réseau en secondes.")
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.2, help="Pause entre pages en secondes.")
    args = parser.parse_args()
    if (args.page_size <= 0 or args.timeout <= 0 or args.retries < 0 or args.delay < 0
            or (args.max_pages is not None and args.max_pages <= 0)):
        parser.error("Tailles, timeout et limite doivent être positifs ; retries et délai non négatifs.")
    try:
        download(args)
    except KeyboardInterrupt:
        print("\nInterrompu. Relancer la même commande pour reprendre.", file=sys.stderr)
        return 130
    except (OSError, EOFError, ValueError, RuntimeError, KeyError) as error:
        print(f"Échec : {error}\nLots conservés ; corriger la cause puis relancer.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
