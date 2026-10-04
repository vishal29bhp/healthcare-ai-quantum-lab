"""Build every catalogue output from the metadata records, assessments, manifest and validation log.

Inputs (all in catalog/ unless noted):
  records/*.json          verified metadata, one array per category (source of truth)
  assessments.csv         suitability assessments and numeric sizes used for QML estimates (our judgement)
  repositories.json       repository registry and search methods
  acquisition_manifest.csv, ../logs/validation_log.csv   evidence for download/parse/preprocess stages
Outputs:
  master_catalog.csv, master_catalog.xlsx, category_views/*.csv, source_registry.csv,
  access_restrictions.csv, overlaps.csv, qml_feasibility_matrix.csv,
  ../documentation/category_catalogue.md, ../documentation/source_license_report.md,
  README.md in each <category>/<subcategory>/ folder
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from . import CATALOG_DIR, ROOT
from .acquire import MANIFEST_PATH
from .qml import estimate
from .records import find_overlaps, load_records, validate_record
from .schema import CATEGORIES, MANIFEST_COLUMNS, MASTER_COLUMNS, NOT_REPORTED
from .status import derive_status, read_csv_rows, status_label
from .validate import VALIDATION_LOG

ASSESSMENTS = CATALOG_DIR / "assessments.csv"
REPOSITORIES = CATALOG_DIR / "repositories.json"
DOCS = ROOT / "documentation"

ACCESS_TEXT = {
    "open": "Open (no login)",
    "registration": "Registration / click-through terms",
    "credentialed": "Credentialed access (training + DUA)",
    "controlled": "Controlled access (application / DUA approval)",
    "competition": "Competition rules acceptance (account required)",
    "unknown": "Not verified",
}


def _cell(value) -> str:
    text = str(value).strip() if value is not None else ""
    return text or NOT_REPORTED


def read_assessments(path: Path = ASSESSMENTS) -> dict[str, dict]:
    return {row["dataset_id"]: row for row in read_csv_rows(path)}


def master_row(record: dict, assessment: dict, status: str) -> dict:
    access = ACCESS_TEXT.get(record["access_level"], record["access_level"])
    prereq = record.get("access_prerequisites", "")
    if prereq and prereq not in (NOT_REPORTED, "None", "none"):
        access = f"{access}: {prereq}"
    return {
        "Dataset ID": record["dataset_id"],
        "Dataset Name": record["name"],
        "Category": record["category"],
        "Subcategory": record["subcategory"],
        "Repository": record["repository"],
        "Canonical URL": record["canonical_url"],
        "DOI": record["doi"],
        "Modality": record["modality"],
        "Sample Count": record["sample_count"],
        "Feature Count": record["feature_count"],
        "Target": record["target"],
        "File Format": record["file_formats"],
        "License": record["license"],
        "Access Requirements": access,
        "Download Method": record["download_method"],
        "Dataset Version": record["version"],
        "Classical ML Suitability": _cell(assessment.get("classical_ml_suitability")),
        "QML Suitability": _cell(assessment.get("qml_suitability")),
        "Verification Status": status_label(status),
        "Limitations": record["limitations"],
        "Citation": record["citation"],
    }


def qml_rows(records: dict[str, dict], assessments: dict[str, dict]) -> list[dict]:
    rows = []
    for dataset_id, record in records.items():
        a = assessments.get(dataset_id, {})
        try:
            n, d = int(a["n_samples"]), int(a["n_features"])
        except (KeyError, ValueError):
            continue  # no numeric size (databases, image corpora without a fixed tabular view)
        q = int(a.get("target_qubits") or 8)
        est = estimate(n, d, target_qubits=q)
        rows.append({
            "dataset_id": dataset_id,
            "name": record["name"],
            "task": a.get("task", ""),
            "n_samples_used": n,
            "n_features_raw": d,
            "size_basis": a.get("size_basis", ""),
            "label_structure": a.get("label_structure", ""),
            "class_imbalance": a.get("class_imbalance", ""),
            "reduction": a.get("reduction", ""),
            **asdict(est),
            "recommended_encoding": a.get("recommended_encoding", ""),
            "recommended_qml_models": a.get("recommended_qml_models", ""),
            "classical_baselines": a.get("classical_baselines", ""),
            "qml_suitability": a.get("qml_suitability", ""),
            "trainability_notes": a.get("trainability_notes", ""),
        })
    return rows


def write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=columns) if columns else pd.DataFrame(rows)
    frame.to_csv(path, index=False)


def _md_table(frame: pd.DataFrame) -> str:
    def esc(value) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(frame.columns) + " |", "|" + "---|" * len(frame.columns)]
    lines += ["| " + " | ".join(esc(v) for v in row) + " |" for row in frame.itertuples(index=False)]
    return "\n".join(lines)


def write_subcategory_readmes(master: pd.DataFrame, records: dict[str, dict]) -> None:
    for (category, subcategory), group in master.groupby(["Category", "Subcategory"]):
        folder = ROOT / CATEGORIES[category] / subcategory
        folder.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# {category} / {subcategory}",
            "",
            "Generated by `python -m hcds.build_catalog`; do not edit by hand.",
            "",
            "Only files whose licence permits local storage are placed under `raw/` (git-ignored). "
            "Restricted datasets are represented here by metadata and access steps only.",
            "",
            _md_table(group[["Dataset ID", "Dataset Name", "Repository", "License", "Access Requirements",
                             "Verification Status"]]),
            "",
        ]
        (folder / "README.md").write_text("\n".join(lines), encoding="utf-8")


def build(check_only: bool = False) -> int:
    records = load_records()
    problems = [p for r in records.values() for p in validate_record(r)]
    if problems:
        print("Record validation failed:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    if check_only:
        print(f"{len(records)} records valid")
        return 0
    assessments = read_assessments()
    manifest = read_csv_rows(MANIFEST_PATH)
    validation = read_csv_rows(VALIDATION_LOG)
    statuses = {i: derive_status(r, manifest, validation) for i, r in records.items()}
    master = pd.DataFrame(
        [master_row(r, assessments.get(i, {}), statuses[i]) for i, r in records.items()], columns=MASTER_COLUMNS
    )
    master.to_csv(CATALOG_DIR / "master_catalog.csv", index=False)

    full = pd.DataFrame(list(records.values()))
    full.insert(full.columns.get_loc("verification_status") + 1, "derived_status",
                full["dataset_id"].map(lambda i: status_label(statuses[i])))
    full.to_csv(CATALOG_DIR / "master_catalog_full_metadata.csv", index=False)

    for category, slug in CATEGORIES.items():
        master[master["Category"] == category].to_csv(CATALOG_DIR / "category_views" / f"{slug}.csv", index=False)

    restricted = [
        {
            "dataset_id": r["dataset_id"], "name": r["name"], "repository": r["repository"],
            "access_level": r["access_level"], "license": r["license"],
            "access_prerequisites": r["access_prerequisites"], "canonical_url": r["canonical_url"],
            "next_step": "Complete the listed prerequisites yourself, then add the file to acquisition_plan.csv "
                         "only if the licence permits local storage; this tool never downloads non-open data.",
        }
        for r in records.values() if r["access_level"] != "open"
    ]
    write_csv(CATALOG_DIR / "access_restrictions.csv", restricted)

    overlaps = [{"dataset_id_a": a, "dataset_id_b": b, "reason": why} for a, b, why in find_overlaps(records)]
    mirror_rows = [
        {"dataset_id_a": r["dataset_id"], "dataset_id_b": "", "reason": f"mirrors: {r['mirrors']}"}
        for r in records.values() if r["mirrors"] not in (NOT_REPORTED, "None", "")
    ]
    known = [
        {"dataset_id_a": r["dataset_id_a"], "dataset_id_b": r["dataset_id_b"],
         "reason": f"{r['relationship']}: {r['basis']}"}
        for r in read_csv_rows(CATALOG_DIR / "known_relationships.csv")
    ]
    mirror_rows = known + mirror_rows
    write_csv(CATALOG_DIR / "overlaps.csv", overlaps + mirror_rows, ["dataset_id_a", "dataset_id_b", "reason"])

    qml = qml_rows(records, assessments)
    write_csv(CATALOG_DIR / "qml_feasibility_matrix.csv", qml)

    registry = json.loads(REPOSITORIES.read_text(encoding="utf-8"))
    repo_counts = Counter()
    for r in records.values():  # first matching registry entry wins, so no dataset is counted twice
        haystack = f"{r['repository']} {r['canonical_url']}".lower()
        repo = next((g for g in registry if any(k.lower() in haystack for k in g["match"])), None)
        repo_counts[repo["repository"] if repo else "Unmatched"] += 1
    registry_rows = [{**{k: v for k, v in repo.items() if k != "match"},
                      "datasets_in_catalogue": repo_counts[repo["repository"]]} for repo in registry]
    write_csv(CATALOG_DIR / "source_registry.csv", registry_rows)

    if not MANIFEST_PATH.exists():
        write_csv(MANIFEST_PATH, [], MANIFEST_COLUMNS)

    with pd.ExcelWriter(CATALOG_DIR / "master_catalog.xlsx", engine="openpyxl") as writer:
        master.to_excel(writer, sheet_name="Master", index=False)
        for category, slug in CATEGORIES.items():
            master[master["Category"] == category].to_excel(writer, sheet_name=slug[:31], index=False)
        full.to_excel(writer, sheet_name="Full metadata", index=False)
        pd.DataFrame(registry_rows).to_excel(writer, sheet_name="Source registry", index=False)
        pd.DataFrame(restricted).to_excel(writer, sheet_name="Access restrictions", index=False)
        pd.DataFrame(qml).to_excel(writer, sheet_name="QML feasibility", index=False)
        pd.read_csv(MANIFEST_PATH).to_excel(writer, sheet_name="Acquisition manifest", index=False)
        pd.DataFrame(overlaps + mirror_rows).to_excel(writer, sheet_name="Overlaps & mirrors", index=False)
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "B2"
            sheet.auto_filter.ref = sheet.dimensions

    write_subcategory_readmes(master, records)
    write_reports(master, records, statuses)
    counts = Counter(statuses.values())
    print(f"{len(records)} datasets; status counts: {dict(counts)}")
    return 0


def write_reports(master: pd.DataFrame, records: dict[str, dict], statuses: dict[str, str]) -> None:
    DOCS.mkdir(exist_ok=True)
    out = ["# Category-wise dataset catalogue", "",
           "Generated from `catalog/records/*.json` by `python -m hcds.build_catalog`. Counts, licences and access "
           "terms are repository-provided claims recorded on the verification date; suitability columns are our "
           "assessments.", ""]
    for category in CATEGORIES:
        group = master[master["Category"] == category]
        out += [f"## {category} ({len(group)} datasets)", "",
                _md_table(group[["Dataset ID", "Dataset Name", "Subcategory", "Sample Count", "Target",
                                 "Access Requirements", "Verification Status", "Canonical URL"]]), ""]
    (DOCS / "category_catalogue.md").write_text("\n".join(out), encoding="utf-8")

    lic = pd.DataFrame([
        {"Dataset ID": i, "Dataset Name": r["name"], "License (as stated)": r["license"],
         "Access level": r["access_level"], "Verified on": r["verified_on"],
         "Method": r["verification_method"], "Status": status_label(statuses[i])}
        for i, r in records.items()
    ])
    summary = lic["Access level"].value_counts().rename_axis("Access level").reset_index(name="Datasets")
    report = ["# Source and licence verification report", "",
              "Licence text is copied from the dataset's own landing page or metadata API. 'Not reported' means the "
              "page we fetched did not state a licence; it does **not** mean the data is unrestricted. Always "
              "re-read the licence before redistribution.", "", "## Access levels", "", _md_table(summary), "",
              "## Per-dataset licence and verification", "", _md_table(lic), ""]
    (DOCS / "source_license_report.md").write_text("\n".join(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Only validate records")
    return build(check_only=parser.parse_args(argv).check)


if __name__ == "__main__":
    raise SystemExit(main())
