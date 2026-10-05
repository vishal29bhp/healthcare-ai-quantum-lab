"""Index every dataset we hold data for: how much there is and where to find it.

Volumes come from evidence only: file sizes from the acquisition manifest, row and record counts from the last
successful ``parsed`` entry in logs/validation_log.csv, and Snowflake row counts from the catalogue record (the
tables themselves stay in Snowflake). Writes catalog/data_volumes.csv and documentation/data_volumes.md.

    python -m hcds.volumes
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from . import CATALOG_DIR, LOG_DIR, RECORDS_DIR, ROOT
from .status import read_csv_rows

MANIFEST_PATH = CATALOG_DIR / "acquisition_manifest.csv"
VALIDATION_LOG = LOG_DIR / "validation_log.csv"
PARSE_CONFIG = CATALOG_DIR / "parse_config.json"
OUT_CSV = CATALOG_DIR / "data_volumes.csv"
OUT_MD = ROOT / "documentation" / "data_volumes.md"

COLUMNS = ["dataset_id", "name", "category", "status", "source", "location", "files", "size_mb", "volume",
           "source_reported_size", "read_by"]

# Code that loads a dataset beyond the generic hcds.pipeline / hcds.validate pass every download gets.
READERS = {
    "CLN-001": "scripts/hcds/experiments.py (E3, load_heart)",
    "CLN-002": "scripts/hcds/experiments.py (E2, load_pima)",
    "CLN-003": "scripts/hcds/experiments.py (E4, load_readmission)",
    "CLN-009": "scripts/hcds/benchmark.py --dataset-id CLN-009 (E1)",
    "BIO-003": "scripts/hcds/rnaseq.py (E5)",
    "TS-001": "scripts/hcds/ecg.py (E7)",
}
GENERIC_READER = "scripts/hcds/validate.py (hcds.pipeline)"
SNOWFLAKE_READER = "scripts/hcds/snowflake_source.py (aggregates only)"


def _records() -> dict[str, dict]:
    records = {}
    for path in sorted(RECORDS_DIR.glob("*.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            records[record["dataset_id"]] = record
    return records


def describe_parse(details: str) -> str:
    """Turn a ``parsed`` validation detail (JSON, possibly truncated) into a short volume phrase."""
    try:
        info = json.loads(details)
    except json.JSONDecodeError:
        info = {}
        for key in ("rows", "columns", "total_rows", "total_columns", "tables_parsed", "wfdb_records", "edf_files"):
            marker = f'"{key}": '
            if marker in details:
                digits = details.split(marker, 1)[1].split(",", 1)[0].split("}", 1)[0].strip()
                if digits.isdigit():
                    info[key] = int(digits)
    if "rows" in info:
        return f"{info['rows']:,} rows x {info.get('columns', '?')} cols"
    if "total_rows" in info:
        return f"{info['total_rows']:,} rows in {info.get('tables_parsed', '?')} tables"
    if "wfdb_records" in info:
        return f"{info['wfdb_records']:,} WFDB signal records"
    if "edf_files" in info:
        return f"{info['edf_files']:,} EDF recordings"
    return "Parsed (no count logged)"


def build_rows() -> list[dict]:
    records = _records()
    manifest = read_csv_rows(MANIFEST_PATH)
    validation = read_csv_rows(VALIDATION_LOG)

    parsed = {}
    for row in validation:
        if row["stage"] == "parsed" and row["ok"] == "true":
            parsed[row["dataset_id"]] = row["details"]

    local = defaultdict(dict)  # dataset_id -> {local_path: bytes}, latest success wins
    snowflake = defaultdict(dict)  # snowflake database -> {local_path: bytes}
    for row in manifest:
        size = int(float(row["file_size_bytes"] or 0))
        if row["dataset_id"].startswith("SNOWFLAKE-") and row["download_status"] == "aggregated":
            snowflake[row["requested_files"].split(".", 1)[0]][row["local_path"]] = size
        elif row["download_status"] == "success" and row.get("sha256"):
            local[row["dataset_id"]][row["local_path"]] = size

    rows = []
    for dataset_id, files in local.items():
        record = records.get(dataset_id, {})
        folders = sorted({str(Path(p).parent) + "/" for p in files})
        rows.append({
            "dataset_id": dataset_id, "name": record.get("name", ""), "category": record.get("category", ""),
            "status": "", "source": "Downloaded file (git-ignored raw/)", "location": "; ".join(folders),
            "files": len(files), "size_mb": round(sum(files.values()) / 1e6, 2),
            "volume": describe_parse(parsed[dataset_id]) if dataset_id in parsed else "Not parsed yet",
            "source_reported_size": record.get("sample_count", ""),
            "read_by": "; ".join(filter(None, [READERS.get(dataset_id), GENERIC_READER])),
        })
    for dataset_id, record in records.items():
        url = record.get("download_or_api_url", "")
        if not url.startswith("snowflake://"):
            continue
        fqn = url.removeprefix("snowflake://")
        profiles = snowflake.get(fqn.split(".", 1)[0], {})
        rows.append({
            "dataset_id": dataset_id, "name": record["name"], "category": record["category"], "status": "",
            "source": "Snowflake (owner's account)", "location": f"{fqn} (profiles: snowflake/raw/profiles/)",
            "files": len(profiles), "size_mb": round(sum(profiles.values()) / 1e6, 2),
            "volume": f"{record['sample_count']} in Snowflake; only aggregate profiles held locally",
            "source_reported_size": record.get("sample_count", ""), "read_by": SNOWFLAKE_READER,
        })

    status = {r["Dataset ID"]: r["Verification Status"] for r in read_csv_rows(CATALOG_DIR / "master_catalog.csv")}
    for row in rows:
        row["status"] = status.get(row["dataset_id"], "")
    return sorted(rows, key=lambda r: (r["source"].startswith("Snowflake"), -r["size_mb"]))


def to_markdown(rows: list[dict]) -> str:
    local = [r for r in rows if not r["source"].startswith("Snowflake")]
    cloud = [r for r in rows if r["source"].startswith("Snowflake")]
    total_mb = sum(r["size_mb"] for r in local)
    lines = [
        "# Data volumes and locations",
        "",
        "Generated by `python -m hcds.volumes` from the acquisition manifest, `logs/validation_log.csv` and the "
        "catalogue records. Do not edit by hand.",
        "",
        f"- **Downloaded:** {len(local)} datasets, {sum(r['files'] for r in local)} files, "
        f"{total_mb / 1000:.2f} GB. Files sit under `healthcare-datasets/<category>/<subcategory>/raw/<ID>/` and "
        "are git-ignored, so run `python -m hcds.pipeline` to fetch them on a new machine.",
        f"- **Snowflake:** {len(cloud)} catalogue entries. The tables stay in the owner's Snowflake account; only "
        "aggregate profiles (cells with n<11 suppressed) are written to the git-ignored `snowflake/raw/` folder.",
        "- Every other catalogue entry is metadata only (no data held).",
        "",
        "## Downloaded datasets",
        "",
        "| ID | Dataset | Status | Size (MB) | Files | Parsed volume | Source-reported size | Folder | Read by |",
        "|---|---|---|---:|---:|---|---|---|---|",
    ]
    for r in local:
        lines.append(f"| {r['dataset_id']} | {r['name']} | {r['status']} | {r['size_mb']:,.2f} | {r['files']} | "
                     f"{r['volume']} | {r['source_reported_size']} | `{r['location']}` | {_code(r['read_by'])} |")
    lines += [
        "",
        "## Snowflake datasets",
        "",
        "| ID | Dataset | Rows in Snowflake | Snowflake object | Local aggregate files | Read by |",
        "|---|---|---|---|---:|---|",
    ]
    for r in cloud:
        fqn, _, folder = r["location"].partition(" (")
        lines.append(f"| {r['dataset_id']} | {r['name']} | {r['source_reported_size']} | `{fqn}` | "
                     f"{r['files']} ({r['size_mb']:.2f} MB) | {_code(r['read_by'])} |")
    return "\n".join(lines) + "\n"


def _code(text: str) -> str:
    return "<br>".join(f"`{part.split(' (')[0]}`" + (f" ({part.split(' (', 1)[1]}" if " (" in part else "")
                       for part in text.split("; "))


def main() -> int:
    rows = build_rows()
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    OUT_MD.write_text(to_markdown(rows), encoding="utf-8")
    print(f"wrote {len(rows)} rows to {OUT_CSV.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
