from io import BytesIO

import pandas as pd
import pytest

from healthcare_lab.data import check_dataset, fingerprint_dataset, load_dataset, profile_dataset, validate_upload


def test_profile_and_fingerprint_are_descriptive_and_stable():
    frame = pd.DataFrame({"age": [20, None, 20], "label": ["a", "b", "a"]})
    profile = profile_dataset(frame)
    assert profile["rows"] == 3
    assert profile["missing_values"]["age"] == 1
    assert profile["duplicate_rows"] == 1
    assert fingerprint_dataset(frame) == fingerprint_dataset(frame.copy())


def test_upload_validation_and_csv_loading():
    assert validate_upload("records.csv", 5) == ".csv"
    loaded = load_dataset(BytesIO(b"x,y\n1,2\n"), "records.csv")
    assert loaded.shape == (1, 2)
    with pytest.raises(ValueError, match="Only CSV"):
        validate_upload("records.exe", 5)


def test_check_dataset_flags_identifier_constant_missing_and_leakage():
    frame = pd.DataFrame({
        "patient_id": range(12),
        "site": ["A"] * 12,
        "lab": [None] * 8 + [1.0, 2.0, 3.0, 4.0],
        "outcome_copy": ["yes", "no"] * 6,
        "age": [30, 40, 50, 60, 35, 45, 55, 65, 33, 43, 53, 63],
        "outcome": ["yes", "no"] * 6,
    })
    issues = "\n".join(check_dataset(frame, "outcome"))
    assert "`patient_id` looks like an identifier" in issues
    assert "`site` is constant" in issues
    assert "`lab` is 67% missing" in issues
    assert "`outcome_copy` is identical to the target" in issues
    assert "`age`" not in issues


def test_check_dataset_flags_numeric_leakage_and_passes_clean_data():
    ages = [21, 24, 22, 30, 27, 33, 29, 35, 38, 36, 41, 44]
    frame = pd.DataFrame({"age": ages, "stay_days": [age * 2 - 40 for age in ages], "noise": [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8]})
    issues = check_dataset(frame, "stay_days")
    assert any("`age` has correlation 1.00" in issue for issue in issues)
    assert check_dataset(frame.drop(columns=["age"]), "stay_days") == []
