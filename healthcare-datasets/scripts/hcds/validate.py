"""Integrity checks, parsing and profiling for downloaded files.

Reads successful rows of the acquisition manifest, re-hashes each file, tries to parse it, and appends one row
per stage to ``logs/validation_log.csv``. Stages: ``integrity_verified`` and ``parsed``. A stage is logged as
``ok=true`` only when the operation actually succeeded.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import CATALOG_DIR, LOG_DIR, ROOT
from .acquire import MANIFEST_PATH, file_digest

VALIDATION_LOG = LOG_DIR / "validation_log.csv"
PARSE_CONFIG = CATALOG_DIR / "parse_config.json"  # {dataset_id: {"target": ..., "read_options": {...}}}
VALIDATION_COLUMNS = ["dataset_id", "stage", "ok", "timestamp_utc", "details"]
TABULAR_SUFFIXES = (".csv", ".csv.gz", ".tsv", ".data", ".txt")


def append_validation(row: dict, path: Path = VALIDATION_LOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=VALIDATION_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({**row, "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})


def read_tabular(path: Path, **options) -> pd.DataFrame:
    """Parse a tabular file; ``options`` are passed to ``pandas.read_csv`` (e.g. header=None, skiprows=1)."""
    options = {"sep": None, "engine": "python", **options}
    name = path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"Corrupt member in zip: {bad}")
            members = [m for m in archive.namelist() if m.lower().endswith(TABULAR_SUFFIXES)]
            if not members:
                raise ValueError(f"No tabular member in zip (members: {archive.namelist()[:10]})")
            with archive.open(members[0]) as handle:
                return pd.read_csv(io.BytesIO(handle.read()), **options)
    if name.endswith(TABULAR_SUFFIXES):
        return pd.read_csv(path, **options)
    if name.endswith(".arff"):
        from scipy.io import arff

        data, _ = arff.loadarff(path)
        return pd.DataFrame(data)
    raise ValueError(f"No parser registered for {path.name}")


def profile(frame: pd.DataFrame, target: str | None = None) -> dict:
    summary = {
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "missing_cells": int(frame.isna().sum().sum()),
        "columns_with_missing": {str(k): int(v) for k, v in frame.isna().sum().items() if v},
        "duplicate_rows": int(frame.duplicated().sum()),
    }
    if target is not None and target in frame.columns:
        summary["class_distribution"] = {str(k): int(v) for k, v in frame[target].value_counts(dropna=False).items()}
    summary["dtypes"] = {str(k): str(v) for k, v in frame.dtypes.items()}
    return summary


def validate_manifest(manifest_path: Path = MANIFEST_PATH, log_path: Path = VALIDATION_LOG,
                      targets: dict[str, str] | None = None, read_options: dict[str, dict] | None = None,
                      dataset_ids: set[str] | None = None) -> list[dict]:
    targets = targets or {}
    read_options = read_options or {}
    results = []
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if r["download_status"] == "success"
                and (dataset_ids is None or r["dataset_id"] in dataset_ids)]
    for row in rows:
        dataset_id = row["dataset_id"]
        path = ROOT / row["local_path"]
        if not path.exists():
            entry = {"dataset_id": dataset_id, "stage": "integrity_verified", "ok": "false",
                     "details": f"missing file {row['local_path']}"}
            append_validation(entry, log_path)
            results.append(entry)
            continue
        sha = file_digest(path)
        size_ok = str(path.stat().st_size) == row["file_size_bytes"]
        integrity_ok = sha == row["sha256"] and size_ok
        expected = row.get("expected_checksum", "")
        detail = f"sha256 re-hash {'matches' if sha == row['sha256'] else 'DIFFERS from'} manifest; size {'ok' if size_ok else 'differs'}"
        detail += f"; upstream checksum {'compared' if expected else 'not published by source'}"
        entry = {"dataset_id": dataset_id, "stage": "integrity_verified", "ok": str(integrity_ok).lower(), "details": detail}
        append_validation(entry, log_path)
        results.append(entry)
        if not integrity_ok:
            continue
        try:
            frame = read_tabular(path, **read_options.get(dataset_id, {}))
            details = json.dumps(profile(frame, targets.get(dataset_id)))[:2000]
            entry = {"dataset_id": dataset_id, "stage": "parsed", "ok": "true", "details": details}
        except Exception as error:
            entry = {"dataset_id": dataset_id, "stage": "parsed", "ok": "false", "details": f"{type(error).__name__}: {error}"}
        append_validation(entry, log_path)
        results.append(entry)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    config = json.loads(PARSE_CONFIG.read_text()) if PARSE_CONFIG.exists() else {}
    results = validate_manifest(
        targets={k: v["target"] for k, v in config.items() if "target" in v},
        read_options={k: v.get("read_options", {}) for k, v in config.items()},
    )
    for entry in results:
        print(entry["dataset_id"], entry["stage"], entry["ok"], entry["details"][:120])
    return 0 if all(e["ok"] == "true" for e in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
