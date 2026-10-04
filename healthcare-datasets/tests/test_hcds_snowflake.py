"""Offline tests for the Snowflake column classifier (no Snowflake connection needed)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hcds.snowflake_source import classify_column  # noqa: E402


@pytest.mark.parametrize("name,dtype,expected", [
    ("PATIENT_NAME", "TEXT", "direct_identifier"),
    ("FIRST_NAME", "TEXT", "direct_identifier"),
    ("MRN", "TEXT", "direct_identifier"),
    ("SSN", "TEXT", "direct_identifier"),
    ("EMAIL", "TEXT", "direct_identifier"),
    ("ZIP_CODE", "TEXT", "direct_identifier"),
    ("PATIENT_ID", "NUMBER", "direct_identifier"),
    ("ENCOUNTER_KEY", "NUMBER", "direct_identifier"),
    ("DOB", "DATE", "date"),
    ("ADMIT_DATE", "TIMESTAMP_NTZ", "date"),
    ("DEATHS", "NUMBER", "numeric"),
    ("BIRTH_DATE", "TEXT", "date"),
    ("AGE", "NUMBER", "age"),
    ("CITY", "TEXT", "quasi_identifier"),
    ("CLINICAL_NOTES", "TEXT", "free_text"),
    ("GLUCOSE", "FLOAT", "numeric"),
    ("DIAGNOSIS_CODE", "VARCHAR(16)", "categorical"),
    ("SEX", "TEXT", "categorical"),
])
def test_classify_column(name, dtype, expected):
    assert classify_column(name, dtype) == expected
