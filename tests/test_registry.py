import sqlite3

from healthcare_lab.experiments import ExperimentResult
from healthcare_lab.registry import record_experiment


def test_registry_stores_metadata_not_raw_data(tmp_path):
    database = tmp_path / "experiments.sqlite3"
    result = ExperimentResult("classification", "RandomForestClassifier", 42, 9, 3, {"accuracy": 0.8})
    record_experiment(database, "abc123", 12, 3, "outcome", result)
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT dataset_fingerprint, metrics_json FROM experiments").fetchone()
    assert row[0] == "abc123"
    assert "accuracy" in row[1]
