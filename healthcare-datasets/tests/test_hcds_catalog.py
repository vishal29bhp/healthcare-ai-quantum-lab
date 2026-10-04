"""Offline tests for the healthcare dataset catalogue tooling (no network access needed)."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hcds.acquire import PlanRow, acquire, file_digest, _redact  # noqa: E402
from hcds.preprocess import split, validate_preprocessing  # noqa: E402
from hcds.qml import amplitude_qubits, estimate  # noqa: E402
from hcds.records import load_records, validate_record  # noqa: E402
from hcds.schema import MANIFEST_COLUMNS, RECORD_FIELDS  # noqa: E402
from hcds.status import derive_status  # noqa: E402


@pytest.fixture(scope="module")
def records():
    return load_records()


def test_all_records_valid_and_unique(records):
    assert len(records) >= 100
    problems = [p for r in records.values() for p in validate_record(r)]
    assert problems == []


def test_metadata_never_claims_acquisition_stages(records):
    assert {r["verification_status"] for r in records.values()} <= {"discovered", "source_verified", "access_verified"}


def test_validate_record_flags_missing_fields_and_bad_status():
    bad = {field: "x" for field in RECORD_FIELDS}
    bad.update(dataset_id="CLN-999", category="Clinical/Tabular", access_level="open", verification_status="downloaded")
    assert any("may only claim" in p for p in validate_record(bad))
    del bad["license"]
    assert any("missing fields" in p for p in validate_record(bad))


def _record(status="access_verified", access="open"):
    return {"dataset_id": "CLN-900", "verification_status": status, "access_level": access,
            "category": "Clinical/Tabular", "subcategory": "cancer", "access_prerequisites": "None", "version": "1"}


def test_status_requires_evidence_for_each_stage():
    rec = _record()
    assert derive_status(rec, [], []) == "access_verified"
    manifest = [{"dataset_id": "CLN-900", "download_status": "success", "sha256": "ab"}]
    assert derive_status(rec, manifest, []) == "downloaded"
    parsed_only = [{"dataset_id": "CLN-900", "stage": "parsed", "ok": "true"}]
    assert derive_status(rec, manifest, parsed_only) == "downloaded"  # integrity stage missing -> ladder stops
    full = [{"dataset_id": "CLN-900", "stage": s, "ok": "true"}
            for s in ("integrity_verified", "parsed", "preprocessing_validated")]
    assert derive_status(rec, manifest, full) == "preprocessing_validated"
    failed = [{"dataset_id": "CLN-900", "download_status": "failed", "sha256": ""}]
    assert derive_status(rec, failed, full) == "access_verified"


def test_acquire_never_downloads_restricted_or_unapproved(tmp_path):
    manifest = tmp_path / "manifest.csv"
    rows = [
        PlanRow("CLN-901", "https://example.invalid/a.zip", "a.zip", "https", approved=True),
        PlanRow("CLN-902", "https://example.invalid/b.zip", "b.zip", "https", approved=False),
    ]
    recs = {"CLN-901": _record(access="credentialed") | {"dataset_id": "CLN-901"},
            "CLN-902": _record() | {"dataset_id": "CLN-902"}}
    results = acquire(rows, recs, manifest_path=manifest, min_interval_s=0)
    assert [r["download_status"] for r in results] == ["not_attempted", "not_attempted"]
    with manifest.open() as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MANIFEST_COLUMNS
        assert len(list(reader)) == 2


def test_dry_run_writes_nothing(tmp_path):
    manifest = tmp_path / "manifest.csv"
    recs = {"CLN-902": _record() | {"dataset_id": "CLN-902"}}
    out = acquire([PlanRow("CLN-902", "https://example.invalid/b", "b", "https", approved=True)], recs,
                  manifest_path=manifest, dry_run=True)
    assert out[0]["download_status"] == "planned" and not manifest.exists()


def test_redact_and_digest(tmp_path):
    assert _redact("https://h/x.csv?token=SECRET") == "https://h/x.csv?<redacted>"
    f = tmp_path / "f.txt"
    f.write_bytes(b"abc")
    assert file_digest(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _frame(n=120, seed=0):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(rng.normal(size=(n, 6)), columns=[f"f{i}" for i in range(6)])
    frame["site"] = rng.choice(["a", "b"], size=n)
    frame["patient"] = np.repeat(np.arange(n // 3), 3)
    frame["y"] = (frame["f0"] + rng.normal(scale=0.5, size=n) > 0).astype(int)
    frame.loc[[0, 5], "f1"] = np.nan
    return frame


def test_grouped_split_has_no_patient_leakage():
    frame = _frame()
    prepared = split(frame, "y", group="patient")
    train_patients = set(frame.loc[prepared.x_train.index, "patient"])
    test_patients = set(frame.loc[prepared.x_test.index, "patient"])
    assert not train_patients & test_patients


def test_missing_targets_are_reported_not_silently_dropped():
    frame = _frame()
    frame.loc[[1, 2], "y"] = np.nan
    prepared = split(frame, "y")
    assert prepared.dropped_missing_target == 2
    assert any("2 rows without a target" in note for note in prepared.notes)


def test_validate_preprocessing_passes_on_clean_frame():
    outcome = validate_preprocessing(_frame().drop(columns=["patient"]), "y", n_qubits=4)
    assert outcome["ok"], outcome["checks"]


def test_qml_estimates():
    assert amplitude_qubits(30) == 5
    est = estimate(569, 30, target_qubits=4)
    assert est.angle_qubits == 4 and est.zz_feature_map_entanglers == 6
    assert est.simulator_tier.startswith("CPU")
    assert estimate(10, 64, target_qubits=40).simulator_tier.startswith("requires further reduction")


def test_read_tabular_json_dict_of_records(tmp_path):
    from hcds.validate import profile, read_tabular

    path = tmp_path / "qa.json"
    path.write_text('{"1": {"q": "a?", "ctx": ["x", "y"], "label": "yes"}, "2": {"q": "b?", "ctx": ["z"], "label": "no"}}')
    frame = read_tabular(path)
    assert list(frame["id"]) == ["1", "2"] and len(frame) == 2
    assert profile(frame, "label")["duplicate_rows"] == 0


def test_parse_archive_tables_reads_tarball_inside_zip(tmp_path):
    import io
    import tarfile
    import zipfile

    from hcds.validate import parse_archive_tables

    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w:gz") as tar:
        for name, text in (("set/data.csv", "id,g1,g2\ns1,1,2\ns2,3,4\n"), ("set/labels.csv", "id,Class\ns1,A\ns2,B\n")):
            payload = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("set.tar.gz", tar_bytes.getvalue())
    result = parse_archive_tables(path)
    assert result["tables_parsed"] == 2 and result["total_rows"] == 4 and result["total_columns"] == 5
