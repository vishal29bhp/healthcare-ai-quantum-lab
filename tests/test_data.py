from io import BytesIO

import pandas as pd
import pytest

from healthcare_lab.data import fingerprint_dataset, load_dataset, profile_dataset, validate_upload


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
