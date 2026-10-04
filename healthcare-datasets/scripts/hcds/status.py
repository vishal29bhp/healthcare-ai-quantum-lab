"""Derive each dataset's verification status from evidence, never from assertion.

- discovered / source_verified / access_verified come from the metadata record (and its verified_on date);
- downloaded needs a ``success`` row with a SHA-256 in the acquisition manifest;
- integrity_verified / parsed / preprocessing_validated need ``ok=true`` rows in logs/validation_log.csv.
Each stage only counts when every earlier stage also holds.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .schema import STATUS_LADDER, STATUS_LABELS


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def evidence_stages(dataset_id: str, manifest: list[dict], validation: list[dict]) -> set[str]:
    stages = set()
    if any(r["dataset_id"] == dataset_id and r["download_status"] == "success" and r.get("sha256") for r in manifest):
        stages.add("downloaded")
    for row in validation:
        if row["dataset_id"] == dataset_id and row["ok"] == "true":
            stages.add(row["stage"])
    return stages


def derive_status(record: dict, manifest: list[dict], validation: list[dict]) -> str:
    achieved = {"discovered"}
    claimed = record["verification_status"]
    achieved.update(STATUS_LADDER[1:STATUS_LADDER.index(claimed) + 1])
    achieved |= evidence_stages(record["dataset_id"], manifest, validation)
    status = "discovered"
    for stage in STATUS_LADDER:
        if stage not in achieved:
            break
        status = stage
    return status


def status_label(status: str) -> str:
    return STATUS_LABELS[status]
