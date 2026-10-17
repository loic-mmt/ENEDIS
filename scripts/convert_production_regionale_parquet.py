#!/usr/bin/env python3
"""Convert completed Enedis JSON downloads to a Hive-partitioned Parquet dataset."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from download_production_regionale import atomic_json, exclusive_download, validate_page

ROOT = Path(__file__).resolve().parents[1]
PARIS = ZoneInfo("Europe/Paris")


def arrow_schema(metadata):
    types = {"string": pa.string(), "integer": pa.int64(), "number": pa.float64(),
             "boolean": pa.bool_()}
    fields = []
    for field in metadata["schema"]:
        key = field["key"]
        fields.append(pa.field(key, pa.timestamp("us", tz="UTC") if key == "horodate"
                               else types[field["type"]]))
    # Preserve exact original timestamp spelling and the API's technical score.
    fields.extend([pa.field("horodate_source", pa.string()), pa.field("_score", pa.float64())])
    return pa.schema(fields)


def convert(source, output, batch_pages=100, rows_per_file=500_000):
    source, output = source.resolve(), output.resolve()
    checkpoint = json.loads((source / "checkpoint.json").read_text())
    metadata = json.loads((source / "metadata.json").read_text())
    if (not checkpoint.get("complete") or checkpoint.get("next")
            or checkpoint["downloaded"] != checkpoint["total"]
            or checkpoint["total"] != metadata["count"]):
        raise ValueError("Téléchargement incomplet ou métadonnées incohérentes.")
    expected = [source / f"page-{n:06d}.json.gz" for n in range(1, checkpoint["pages"] + 1)]
    if set(source.glob("page-*.json.gz")) != set(expected):
        raise ValueError("Liste des pages incohérente avec le checkpoint.")
    if output.exists():
        raise FileExistsError(f"Destination déjà présente : {output}. Choisir un autre --output.")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(output.name + ".building")
    # A failed run remains separate from the published dataset.
    stage.mkdir()
    schema = arrow_schema(metadata)
    allowed = set(schema.names) - {"horodate_source"}
    buffers, writers, file_rows, file_numbers = {}, {}, Counter(), Counter()
    counts = Counter()
    total = 0
    minimum = maximum = None
    validation_state = {"total": checkpoint["total"], "downloaded": 0, "next": None}
    previous_next = None

    def flush():
        for year, rows in buffers.items():
            if not rows:
                continue
            table = pa.Table.from_pylist(rows, schema=schema)
            position = 0
            while position < table.num_rows:
                if year not in writers:
                    partition = stage / f"year={year}"
                    partition.mkdir(exist_ok=True)
                    file_numbers[year] += 1
                    writers[year] = pq.ParquetWriter(
                        partition / f"part-{file_numbers[year]:05d}.parquet", schema,
                        compression="zstd", use_dictionary=True, write_statistics=True)
                    file_rows[year] = 0
                size = min(rows_per_file - file_rows[year], table.num_rows - position)
                writers[year].write_table(table.slice(position, size), row_group_size=64_000)
                position += size
                file_rows[year] += size
                if file_rows[year] == rows_per_file:
                    writers.pop(year).close()
            rows.clear()

    try:
        for number, path in enumerate(expected, 1):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                envelope = json.load(stream)
            if number > 1 and envelope["request_url"] != previous_next:
                raise ValueError(f"Chaîne de pagination rompue : {path.name}")
            page = envelope["response"]
            validation_state["next"] = envelope["request_url"]
            validate_page(page, validation_state)
            previous_next = page.get("next")
            for original in page["results"]:
                unknown = set(original) - allowed
                if unknown:
                    raise ValueError(f"Colonnes inconnues : {sorted(unknown)}")
                row = dict(original)
                timestamp = datetime.fromisoformat(row["horodate"].replace("Z", "+00:00"))
                if timestamp.utcoffset() is None:
                    raise ValueError("Horodate sans fuseau horaire.")
                year = timestamp.astimezone(PARIS).year
                utc = timestamp.astimezone(timezone.utc)
                row["horodate_source"] = row["horodate"]
                row["horodate"] = utc
                minimum = min(minimum, utc) if minimum else utc
                maximum = max(maximum, utc) if maximum else utc
                buffers.setdefault(year, []).append(row)
                counts[year] += 1
                total += 1
            validation_state["downloaded"] = total
            if number % batch_pages == 0 or number == len(expected):
                flush()
                print(f"Conversion : {number:,}/{len(expected):,} pages ; {total:,} lignes.", flush=True)
        if total != checkpoint["total"] or previous_next:
            raise ValueError("Nombre de lignes final ou curseur final incohérent.")
    finally:
        for writer in writers.values():
            writer.close()

    # Re-read all Parquet footers, then scan timestamps only to validate routing.
    stored_counts = Counter()
    file_count = 0
    for path in sorted(stage.glob("year=*/*.parquet")):
        year = int(path.parent.name.split("=")[1])
        parquet = pq.ParquetFile(path)
        if not parquet.schema_arrow.equals(schema):
            raise ValueError(f"Schéma incorrect : {path}")
        stored_counts[year] += parquet.metadata.num_rows
        file_count += 1
    if stored_counts != counts:
        raise ValueError("Comptages Parquet différents des comptages JSON.")
    for year in counts:
        partition = ds.dataset(stage / f"year={year}", format="parquet")
        for batch in partition.scanner(columns=["horodate"]).to_batches():
            local = pc.cast(batch.column(0), pa.timestamp("us", tz="Europe/Paris"))
            if not pc.all(pc.equal(pc.year(local), year)).as_py():
                raise ValueError(f"Horodate dans une mauvaise partition : {year}")
    report = {
        "complete": True, "source": str(source), "source_revision": checkpoint["revision"],
        "source_pages": len(expected), "rows": total,
        "rows_by_year": {str(year): counts[year] for year in sorted(counts)},
        "files": file_count, "partition_timezone": "Europe/Paris",
        "timestamp_timezone": "UTC", "min_timestamp_utc": minimum.isoformat(),
        "max_timestamp_utc": maximum.isoformat(),
        "parquet_bytes": sum(p.stat().st_size for p in stage.glob("year=*/*.parquet")),
        "global_duplicate_check": "not_performed",
    }
    atomic_json(stage / "_conversion.json", report)
    (stage / "_schema.txt").write_text(str(schema) + "\n")
    stage.rename(output)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print(f"Dataset validé : {output}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/raw/production_regionale")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/production_regionale")
    parser.add_argument("--batch-pages", type=int, default=100)
    parser.add_argument("--rows-per-file", type=int, default=500_000)
    args = parser.parse_args()
    if args.batch_pages <= 0 or args.rows_per_file <= 0:
        parser.error("Tailles de lots et de fichiers strictement positives requises.")
    try:
        # Use the downloader's lock so the source cannot be changed by it.
        with exclusive_download(args.source):
            convert(args.source, args.output, args.batch_pages, args.rows_per_file)
    except (OSError, ValueError, KeyError, RuntimeError, pa.ArrowException) as error:
        print(f"Échec : {error}. JSON conservés ; sortie partielle éventuelle en .building.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
