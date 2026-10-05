"""Offline tests for the data-volume index (reads the committed catalogue, manifest and validation log)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hcds.volumes import build_rows, describe_parse  # noqa: E402


def test_describe_parse_shapes():
    assert describe_parse('{"rows": 1200, "columns": 9}') == "1,200 rows x 9 cols"
    assert describe_parse('{"tables_parsed": 2, "total_rows": 5000}') == "5,000 rows in 2 tables"
    assert describe_parse('{"wfdb_records": 48, "signals": ["MLII"]}') == "48 WFDB signal records"
    # validation details are cut at 2,000 characters, so the JSON can be incomplete
    assert describe_parse('{"edf_files": 1526, "signals": ["Fc5.", "Fc3') == "1,526 EDF recordings"


def test_build_rows_covers_downloads_and_snowflake():
    rows = build_rows()
    ids = {r["dataset_id"] for r in rows}
    assert {"CLN-001", "TS-001", "PH-019", "NLP-020"} <= ids
    assert all(r["size_mb"] >= 0 and r["location"] for r in rows)
