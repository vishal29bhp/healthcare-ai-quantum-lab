"""Integrity checks, parsing and profiling for downloaded files.

Reads successful rows of the acquisition manifest, re-hashes each file, tries to parse it, and appends one row
per stage to ``logs/validation_log.csv``. Stages: ``integrity_verified`` and ``parsed``. A stage is logged as
``ok=true`` only when the operation actually succeeded.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
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


def verify_sha256sums(path: Path) -> tuple[bool, str] | None:
    """Check every member listed in a SHA256SUMS.txt inside a zip (PhysioNet ships one). None if there is none."""
    if not path.name.lower().endswith(".zip"):
        return None
    with zipfile.ZipFile(path) as archive:
        sums = [m for m in archive.namelist() if m.endswith("SHA256SUMS.txt")]
        if not sums:
            return None
        prefix = sums[0][: -len("SHA256SUMS.txt")]
        members = set(archive.namelist())
        listed = mismatched = missing = 0
        for line in archive.read(sums[0]).decode("utf-8").splitlines():
            if not line.strip():
                continue
            expected, name = line.split(maxsplit=1)
            listed += 1
            member = prefix + name.strip().lstrip("*")
            if member not in members:
                missing += 1
                continue
            digest = hashlib.sha256()
            with archive.open(member) as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            mismatched += digest.hexdigest() != expected.lower()
    ok = listed > 0 and mismatched == 0 and missing == 0
    return ok, f"SHA256SUMS.txt: {listed - mismatched - missing}/{listed} members match ({mismatched} differ, {missing} missing)"


def parse_wfdb_archive(path: Path) -> dict | None:
    """Parse every WFDB header in a zip and read one full record's signals. None if the zip has no WFDB records."""
    with zipfile.ZipFile(path) as archive:
        headers = sorted(m for m in archive.namelist() if m.endswith(".hea"))
        if not headers:
            return None
        import tempfile

        import wfdb  # optional dependency, only needed for PhysioNet waveform archives

        with tempfile.TemporaryDirectory() as tmp:
            archive.extractall(tmp)
            parsed = [wfdb.rdheader(str(Path(tmp) / h[:-4])) for h in headers]
            first = next(h for h, rec in zip(headers, parsed) if rec.n_sig and not getattr(rec, "seg_name", None))
            record = wfdb.rdrecord(str(Path(tmp) / first[:-4]))
    return {"wfdb_records": len(parsed), "signals": sorted({s for rec in parsed for s in (rec.sig_name or [])})[:20],
            "sampling_hz": sorted({float(rec.fs) for rec in parsed}),
            "read_record": Path(first).stem, "read_record_samples": int(record.sig_len),
            "read_record_nan": int(np.isnan(record.p_signal).sum())}


def read_csv_skipping_preamble(payload: bytes, compression: str | None = None) -> pd.DataFrame:
    """Read a CSV, skipping metadata lines above the header if a plain read fails.

    World Bank bulk downloads start with '"Data Source","World Development Indicators",' and a
    '"Last Updated Date",...' line before the real header; the header is taken to be the first of the
    leading lines with the widest field count.
    """
    try:
        return pd.read_csv(io.BytesIO(payload), compression=compression, low_memory=False)
    except pd.errors.ParserError:
        if compression:
            raise
    head = payload.decode("utf-8-sig", errors="replace").splitlines()[:50]
    widths = [len(fields) for fields in csv.reader(head)]
    if not widths:
        raise ValueError("empty CSV")
    header = widths.index(max(widths))
    return pd.read_csv(io.BytesIO(payload), skiprows=header, low_memory=False, encoding="utf-8-sig")


def parse_archive_tables(path: Path) -> dict | None:
    """Parse every CSV (plain, .csv.gz, or inside one level of nested zip or .tar.gz) in a multi-table archive.

    Used for archives that hold many tables (MIMIC-IV demo, Empatica exports, the UCI RNA-Seq tarball) rather than
    one dataset file.
    None if the archive has at most one CSV. Raises if any table fails to parse, so ``parsed`` stays honest.
    """
    def tables(archive: zipfile.ZipFile, prefix: str = ""):
        for name in archive.namelist():
            lower = name.lower()
            if lower.endswith((".csv", ".csv.gz")):
                yield prefix + name, archive.read(name), "gzip" if lower.endswith(".gz") else None
            elif lower.endswith(".zip") and not prefix:
                with zipfile.ZipFile(io.BytesIO(archive.read(name))) as inner:
                    yield from tables(inner, prefix=name + "!")
            elif lower.endswith((".tar.gz", ".tgz")) and not prefix:
                with archive.open(name) as raw, tarfile.open(fileobj=raw, mode="r|gz") as inner:
                    for member in inner:
                        if member.isfile() and member.name.lower().endswith(".csv"):
                            yield f"{name}!{member.name}", inner.extractfile(member).read(), None

    with zipfile.ZipFile(path) as archive:
        found = list(tables(archive))
    if len(found) <= 1:
        return None
    rows, columns, empty = 0, 0, []
    for name, payload, compression in found:
        if not payload.strip():
            empty.append(name)  # e.g. Empatica tags.csv when no event button was pressed
            continue
        try:
            frame = read_csv_skipping_preamble(payload, compression)
        except Exception as error:
            raise ValueError(f"{name}: {type(error).__name__}: {error}") from error
        rows, columns = rows + len(frame), columns + frame.shape[1]
    return {"tables_parsed": len(found) - len(empty), "empty_files": len(empty), "total_rows": rows,
            "total_columns": columns,
            "examples": [name for name, _, _ in found[:5]]}


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
    if name.endswith(".json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):  # {id: {field: value}} as in PubMedQA; the key becomes an "id" column
            return pd.DataFrame.from_dict(data, orient="index").rename_axis("id").reset_index()
        return pd.DataFrame(data)
    if name.endswith(".arff"):
        from scipy.io import arff

        data, _ = arff.loadarff(path)
        frame = pd.DataFrame(data)
        for column in frame.select_dtypes(include="object"):  # nominal ARFF attributes load as bytes
            frame[column] = frame[column].str.decode("utf-8")
        return frame
    raise ValueError(f"No parser registered for {path.name}")


def profile(frame: pd.DataFrame, target: str | None = None) -> dict:
    summary = {
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "missing_cells": int(frame.isna().sum().sum()),
        "columns_with_missing": {str(k): int(v) for k, v in frame.isna().sum().items() if v},
        "duplicate_rows": int(frame.astype(str).duplicated().sum()),  # str: JSON sources hold list cells
    }
    if target is not None and target in frame.columns:
        summary["class_distribution"] = {str(k): int(v) for k, v in frame[target].value_counts(dropna=False).items()}
    summary["dtypes"] = {str(k): str(v) for k, v in frame.dtypes.items()}
    return summary


def validate_manifest(manifest_path: Path = MANIFEST_PATH, log_path: Path = VALIDATION_LOG,
                      targets: dict[str, str] | None = None, read_options: dict[str, dict] | None = None,
                      dataset_ids: set[str] | None = None, files: dict[str, str] | None = None) -> list[dict]:
    """``files`` maps a dataset ID to the one acquired file its parse config describes (others parse generically)."""
    targets = targets or {}
    files = files or {}
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
        member_check = verify_sha256sums(path) if integrity_ok else None
        if member_check:
            integrity_ok = member_check[0]
            detail += f"; {member_check[1]}"
        else:
            detail += f"; upstream checksum {'compared' if expected else 'not published by source'}"
        entry = {"dataset_id": dataset_id, "stage": "integrity_verified", "ok": str(integrity_ok).lower(), "details": detail}
        append_validation(entry, log_path)
        results.append(entry)
        if not integrity_ok:
            continue
        try:
            configured = dataset_id in targets and files.get(dataset_id) in (None, row["requested_files"])
            is_zip = path.name.lower().endswith(".zip")
            archive = None if configured or not is_zip else (parse_wfdb_archive(path) or parse_archive_tables(path))
            if archive:
                details = json.dumps(archive)[:2000]
            else:
                frame = read_tabular(path, **(read_options.get(dataset_id, {}) if configured else {}))
                details = json.dumps(profile(frame, targets.get(dataset_id) if configured else None))[:2000]
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
        files={k: v["file"] for k, v in config.items() if "file" in v},
    )
    for entry in results:
        print(entry["dataset_id"], entry["stage"], entry["ok"], entry["details"][:120])
    return 0 if all(e["ok"] == "true" for e in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
