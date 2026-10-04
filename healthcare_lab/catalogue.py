"""Read-only access to the healthcare dataset catalogue in ``healthcare-datasets/`` for the explorer page.

Metadata comes from ``catalog/records/*.json`` (the source of truth). Verification status is derived live from the
acquisition manifest and validation log with the catalogue's own ``hcds.status`` rules, so the explorer never shows a
status the evidence does not support, even before the generated CSV views are rebuilt.
"""
from __future__ import annotations

import csv
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "healthcare-datasets"

_SCRIPTS = DEFAULT_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from hcds.schema import STATUS_LABELS, STATUS_LADDER  # noqa: E402
from hcds.status import derive_status  # noqa: E402

ACCESS_LABELS = {
    "open": "Open",
    "registration": "Registration",
    "credentialed": "Credentialed",
    "controlled": "Controlled",
    "competition": "Competition",
    "unknown": "Unknown",
}

TABULAR_SUFFIXES = {".csv", ".tsv", ".data", ".tab"}
TEXT_SUFFIXES = {".txt", ".md", ".names", ".arff", ".hea", ".json", ".log", ".xml", ".html", ".sql", ".info"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
PREVIEW_BYTES = 2 * 1024 * 1024


def licence_family(licence: str) -> str:
    """Group the free-text licence strings into a few families that are useful as a filter."""
    text = licence.lower()
    if text.startswith(("not reported", "not verified")) or not text.strip():
        return "Not reported"
    if "physionet credentialed" in text:
        return "PhysioNet credentialed"
    if "dua" in text.split() or any(term in text for term in (
            "data use agreement", "user agreement", "data use restrictions", "terms of use", "terms and conditions",
            "restricted health data license", "affiliate license", "loinc license", "umls", "subscription",
            "commercial licence", "non-commercial:")):
        return "DUA / custom terms"
    if "by-nc" in text or "by nc" in text:
        return "CC BY-NC (non-commercial)"
    if "by-sa" in text or "by sa" in text:
        return "CC BY-SA"
    if "cc0" in text or "public domain" in text:
        return "CC0 / public domain"
    if "open database license" in text or "odbl" in text:
        return "ODbL"
    if "open data commons attribution" in text:
        return "ODC-By"
    if "cc by" in text or "cc-by" in text or "creative commons by" in text or "creative commons attribution" in text:
        return "CC BY"
    if "mit" in text.split() or "mit license" in text or "apache" in text:
        return "MIT / Apache (code licence)"
    return "Other"


def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@dataclass
class Catalogue:
    root: Path
    records: dict[str, dict]
    manifest: list[dict]
    validation: list[dict]
    assessments: dict[str, dict]
    feasibility: dict[str, dict]
    restrictions: dict[str, dict]
    overlaps: list[dict]
    parse_config: dict
    statuses: dict[str, str]

    def rows(self) -> list[dict]:
        """One flat row per dataset for the browse table and filters."""
        rows = []
        for dataset_id, record in self.records.items():
            assessment = self.assessments.get(dataset_id, {})
            rows.append({
                "ID": dataset_id,
                "Name": record["name"],
                "Category": record["category"],
                "Subcategory": record["subcategory"],
                "Repository": record["repository"],
                "Access": ACCESS_LABELS.get(record["access_level"], record["access_level"]),
                "Licence family": licence_family(record["license"]),
                "Licence": record["license"],
                "Status": STATUS_LABELS[self.statuses[dataset_id]],
                "Downloaded": bool(self.local_files(dataset_id)),
                "Modality": record["modality"],
                "Samples": record["sample_count"],
                "Size": record.get("approx_size", ""),
                "Classical ML": assessment.get("classical_ml_suitability", ""),
                "QML": assessment.get("qml_suitability", ""),
            })
        return rows

    def manifest_rows(self, dataset_id: str) -> list[dict]:
        return [row for row in self.manifest if row["dataset_id"] == dataset_id]

    def validation_rows(self, dataset_id: str) -> list[dict]:
        return [row for row in self.validation if row["dataset_id"] == dataset_id]

    def related(self, dataset_id: str) -> list[dict]:
        related = []
        for row in self.overlaps:
            if dataset_id in (row["dataset_id_a"], row["dataset_id_b"]):
                other = row["dataset_id_b"] if row["dataset_id_a"] == dataset_id else row["dataset_id_a"]
                related.append({"ID": other, "Name": self.records.get(other, {}).get("name", ""),
                                "Relationship": row["reason"]})
        return related

    def local_files(self, dataset_id: str) -> list[Path]:
        """Files the manifest records as downloaded that are present on this machine (raw data is not in git)."""
        files = []
        for row in self.manifest_rows(dataset_id):
            if row["download_status"] != "success" or not row["local_path"]:
                continue
            path = self.resolve(row["local_path"])
            if path is not None and path.is_file() and path not in files:
                files.append(path)
        return files

    def resolve(self, relative: str) -> Path | None:
        """Resolve a manifest path, refusing anything that escapes the catalogue root."""
        root = self.root.resolve()
        path = (root / relative).resolve()
        return path if path.is_relative_to(root) else None


def load_catalogue(root: Path | None = None) -> Catalogue:
    root = root or DEFAULT_ROOT
    catalog = root / "catalog"
    records: dict[str, dict] = {}
    for path in sorted((catalog / "records").glob("*.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            records[record["dataset_id"]] = record
    manifest = _read_csv(catalog / "acquisition_manifest.csv")
    validation = _read_csv(root / "logs" / "validation_log.csv")
    return Catalogue(
        root=root,
        records=records,
        manifest=manifest,
        validation=validation,
        assessments={r["dataset_id"]: r for r in _read_csv(catalog / "assessments.csv")},
        feasibility={r["dataset_id"]: r for r in _read_csv(catalog / "qml_feasibility_matrix.csv")},
        restrictions={r["dataset_id"]: r for r in _read_csv(catalog / "access_restrictions.csv")},
        overlaps=_read_csv(catalog / "overlaps.csv"),
        parse_config=_read_json(catalog / "parse_config.json"),
        statuses={i: derive_status(r, manifest, validation) for i, r in records.items()},
    )


def status_order() -> list[str]:
    return [STATUS_LABELS[s] for s in STATUS_LADDER]


def preview_kind(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in TABULAR_SUFFIXES:
        return "table"
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix == ".zip":
        return "zip"
    return "binary"


def zip_members(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as archive:
        return [{"Member": info.filename, "Size (bytes)": info.file_size, "Kind": preview_kind(info.filename)}
                for info in archive.infolist() if not info.is_dir()]


def read_head(path: Path, member: str | None = None, limit: int = PREVIEW_BYTES) -> bytes:
    """Read at most ``limit`` bytes of a file, or of one member of a zip, without unpacking the rest."""
    if member is None:
        with path.open("rb") as handle:
            return handle.read(limit)
    with zipfile.ZipFile(path) as archive, archive.open(member) as handle:
        return handle.read(limit)


def complete_lines(data: bytes, truncated: bool) -> str:
    """Decode a byte prefix, dropping a trailing partial line when the file was cut off."""
    text = data.decode("utf-8", errors="replace")
    if truncated and "\n" in text:
        text = text[: text.rindex("\n") + 1]
    return text


def sniff_separator(text: str, name: str) -> str:
    if Path(name).suffix.lower() == ".tsv":
        return "\t"
    try:
        return csv.Sniffer().sniff(text[:20_000], delimiters=",\t;|").delimiter
    except csv.Error:
        return ","


def table_preview_options(catalogue: Catalogue, dataset_id: str, name: str, in_zip: bool) -> dict:
    """pandas.read_csv options for a preview; the catalogue's parse_config applies to the file it was written for."""
    config = catalogue.parse_config.get(dataset_id, {})
    if config.get("read_options") and not in_zip and Path(name).suffix.lower() == ".csv":
        return dict(config["read_options"])
    return {}
