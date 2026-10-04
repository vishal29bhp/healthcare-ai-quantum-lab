"""Load and validate the per-category metadata records in ``catalog/records/*.json``."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from . import RECORDS_DIR
from .schema import ACCESS_LEVELS, CATEGORIES, METADATA_STATUSES, RECORD_FIELDS, SUBCATEGORIES, category_for_id

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_records(directory: Path = RECORDS_DIR) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            dataset_id = record["dataset_id"]
            if dataset_id in records:
                raise ValueError(f"Duplicate dataset_id {dataset_id} in {path.name}")
            records[dataset_id] = record
    return records


def validate_record(record: dict) -> list[str]:
    """Return a list of schema problems (empty when the record is valid)."""
    problems = []
    dataset_id = record.get("dataset_id", "<missing id>")
    missing = [field for field in RECORD_FIELDS if field not in record]
    if missing:
        problems.append(f"{dataset_id}: missing fields {missing}")
    empty = [field for field in RECORD_FIELDS if field in record and not str(record[field]).strip()]
    if empty:
        problems.append(f"{dataset_id}: empty fields {empty} (use 'Not reported' / 'Not verified')")
    if record.get("category") not in CATEGORIES:
        problems.append(f"{dataset_id}: unknown category {record.get('category')!r}")
    else:
        try:
            if category_for_id(dataset_id) != record["category"]:
                problems.append(f"{dataset_id}: id prefix does not match category {record['category']}")
        except ValueError as error:
            problems.append(str(error))
    if record.get("category") in SUBCATEGORIES and record.get("subcategory") not in SUBCATEGORIES[record["category"]]:
        problems.append(f"{dataset_id}: subcategory {record.get('subcategory')!r} is not a folder of {record['category']}")
    if record.get("access_level") not in ACCESS_LEVELS:
        problems.append(f"{dataset_id}: access_level {record.get('access_level')!r} not in {ACCESS_LEVELS}")
    status = record.get("verification_status")
    if status not in METADATA_STATUSES:
        problems.append(f"{dataset_id}: metadata records may only claim {METADATA_STATUSES}, got {status!r}")
    elif status != "discovered" and not DATE.match(str(record.get("verified_on", ""))):
        problems.append(f"{dataset_id}: {status} requires a verified_on date")
    return problems


def find_overlaps(records: dict[str, dict]) -> list[tuple[str, str, str]]:
    """Return (id_a, id_b, reason) for records sharing a DOI or canonical URL."""
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for dataset_id, record in records.items():
        doi = str(record.get("doi", "")).lower().removeprefix("https://doi.org/").strip()
        if doi.startswith("10."):
            by_key[("doi", doi)].append(dataset_id)
        url = str(record.get("canonical_url", "")).lower().rstrip("/")
        if url.startswith("http"):
            by_key[("url", url)].append(dataset_id)
    overlaps = []
    for (kind, value), ids in by_key.items():
        for other in ids[1:]:
            overlaps.append((ids[0], other, f"same {kind}: {value}"))
    return overlaps
