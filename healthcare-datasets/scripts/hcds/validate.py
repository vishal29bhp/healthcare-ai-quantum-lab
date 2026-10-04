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
PARSE_CONFIG = CATALOG_DIR / "parse_config.json"  # {dataset_id: {"target": ..., "read_options": {...}, "files": {...}}}
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


def file_config(config: dict, dataset_id: str, filename: str) -> dict:
    """Parse settings for one acquired file: the dataset entry, overridden by its ``files[filename]`` entry if any.

    A dataset can have several acquired files with different layouts (e.g. CLN-009's scikit-learn copy and the
    canonical UCI zip), so per-file settings take precedence over the dataset-level ones.
    """
    entry = dict(config.get(dataset_id, {}))
    override = entry.pop("files", {}).get(filename, {})
    return {**entry, **override}


def read_tabular(path: Path, **options) -> pd.DataFrame:
    """Parse a tabular file; ``options`` are passed to ``pandas.read_csv`` (e.g. header=None, skiprows=1)."""
    options = {"sep": None, **options}
    if options["sep"] is None:
        options.setdefault("engine", "python")  # delimiter sniffing needs the python engine
    member = options.pop("member", None)  # zip member to read; default is the first tabular member
    name = path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"Corrupt member in zip: {bad}")
            members = [m for m in archive.namelist() if m.lower().endswith(TABULAR_SUFFIXES)]
            if not members:
                raise ValueError(f"No tabular member in zip (members: {archive.namelist()[:10]})")
            chosen = member or members[0]
            with archive.open(chosen) as handle:
                compression = "gzip" if chosen.lower().endswith(".gz") else None
                return pd.read_csv(io.BytesIO(handle.read()), compression=compression, **options)
    if name.endswith(TABULAR_SUFFIXES):
        return pd.read_csv(path, **options)
    if name.endswith(".arff"):
        from scipy.io import arff

        data, _ = arff.loadarff(path)
        frame = pd.DataFrame(data)
        for column in frame.select_dtypes(include="object"):  # nominal ARFF attributes load as bytes
            frame[column] = frame[column].map(lambda v: v.decode() if isinstance(v, bytes) else v)
        return frame
    raise ValueError(f"No parser registered for {path.name}")


def verify_zip_sha256sums(path: Path) -> tuple[bool, str] | None:
    """Check every member listed in a SHA256SUMS.txt inside the zip (PhysioNet ships one). None if there is none."""
    import hashlib

    with zipfile.ZipFile(path) as archive:
        sums = [m for m in archive.namelist() if m.rsplit("/", 1)[-1] == "SHA256SUMS.txt"]
        if not sums:
            return None
        prefix = sums[0][: -len("SHA256SUMS.txt")]
        names = set(archive.namelist())
        listed = mismatched = missing = 0
        for line in archive.read(sums[0]).decode().splitlines():
            if not line.strip():
                continue
            expected, member = line.split(maxsplit=1)
            listed += 1
            member = prefix + member.strip().lstrip("*")
            if member not in names:
                missing += 1
                continue
            digest = hashlib.sha256()
            with archive.open(member) as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
            mismatched += digest.hexdigest() != expected
    ok = listed > 0 and not (mismatched or missing)
    return ok, f"SHA256SUMS.txt: {listed - mismatched - missing}/{listed} members match ({missing} missing, {mismatched} differ)"


def parse_archive(path: Path, fmt: str) -> dict:
    """Parse a multi-file archive: every WFDB header (``wfdb``) or every CSV member (``archive``)."""
    import tempfile

    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as tmp:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt member in zip: {bad}")
        if fmt == "wfdb":
            import wfdb

            headers = [m for m in archive.namelist() if m.endswith(".hea")]
            if not headers:
                raise ValueError("No WFDB .hea headers in archive")
            archive.extractall(tmp, members=headers)
            records = [wfdb.rdheader(str(Path(tmp) / h[:-4])) for h in headers]
            return {"records": len(records), "signals": sorted({s for r in records for s in (r.sig_name or [])})[:20],
                    "sampling_hz": sorted({float(r.fs) for r in records}),
                    "total_hours": round(sum(r.sig_len / r.fs for r in records if r.sig_len) / 3600, 2)}
        members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
        rows = 0
        for member in members:
            with archive.open(member) as handle:
                rows += len(pd.read_csv(handle, header=None))
        nested = [m for m in archive.namelist() if m.lower().endswith(".zip")]
        if not members and not nested:
            raise ValueError("No CSV or nested zip members")
        return {"csv_members": len(members), "csv_rows": rows, "nested_zips": len(nested)}


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
                      dataset_ids: set[str] | None = None, config: dict | None = None) -> list[dict]:
    """Re-hash and parse each successful download. ``config`` (parse_config.json) takes precedence over the
    per-dataset ``targets``/``read_options`` maps and allows per-file settings."""
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
        member_check = verify_zip_sha256sums(path) if path.suffix.lower() == ".zip" else None
        if member_check is not None:
            integrity_ok = integrity_ok and member_check[0]
            detail += f"; {member_check[1]}"
        elif expected:
            detail += f"; upstream checksum {expected} matched at download"
        else:
            detail += "; upstream checksum not published by source"
        entry = {"dataset_id": dataset_id, "stage": "integrity_verified", "ok": str(integrity_ok).lower(), "details": detail}
        append_validation(entry, log_path)
        results.append(entry)
        if not integrity_ok:
            continue
        if config is not None:
            cfg = file_config(config, dataset_id, path.name)
            options, target = cfg.get("read_options", {}), cfg.get("target")
            if cfg.get("format") in ("wfdb", "archive"):
                try:
                    details = json.dumps({"file": path.name, **parse_archive(path, cfg["format"])})[:2000]
                    entry = {"dataset_id": dataset_id, "stage": "parsed", "ok": "true", "details": details}
                except Exception as error:
                    entry = {"dataset_id": dataset_id, "stage": "parsed", "ok": "false",
                             "details": f"{path.name}: {type(error).__name__}: {error}"}
                append_validation(entry, log_path)
                results.append(entry)
                continue
            if cfg.get("parse") is False:
                entry = {"dataset_id": dataset_id, "stage": "parsed", "ok": "false",
                         "details": f"{path.name}: not parsed as a table ({cfg.get('note', 'see parse_config.json')})"}
                append_validation(entry, log_path)
                results.append(entry)
                continue
        else:
            options, target = read_options.get(dataset_id, {}), targets.get(dataset_id)
        try:
            frame = read_tabular(path, **options)
            details = json.dumps({"file": path.name, **profile(frame, target)})[:2000]
            entry = {"dataset_id": dataset_id, "stage": "parsed", "ok": "true", "details": details}
        except Exception as error:
            entry = {"dataset_id": dataset_id, "stage": "parsed", "ok": "false",
                     "details": f"{path.name}: {type(error).__name__}: {error}"}
        append_validation(entry, log_path)
        results.append(entry)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="*", help="Only validate these dataset IDs")
    args = parser.parse_args(argv)
    config = json.loads(PARSE_CONFIG.read_text()) if PARSE_CONFIG.exists() else {}
    results = validate_manifest(config=config, dataset_ids=set(args.ids) if args.ids else None)
    for entry in results:
        print(entry["dataset_id"], entry["stage"], entry["ok"], entry["details"][:120])
    return 0 if all(e["ok"] == "true" for e in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
