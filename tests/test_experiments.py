import pandas as pd

from healthcare_lab.experiments import run_baseline


def test_classification_baseline_returns_held_out_metrics():
    frame = pd.DataFrame({"age": range(20, 44), "smoker": ["yes", "no"] * 12, "target": ["high", "low"] * 12})
    result = run_baseline(frame, "target", "classification", seed=12)
    assert result.model_name == "RandomForestClassifier"
    assert result.train_rows + result.test_rows == len(frame)
    assert set(result.metrics) == {"accuracy", "f1_weighted"}


def test_regression_baseline_returns_held_out_metrics():
    frame = pd.DataFrame({"age": range(20, 44), "group": ["a", "b"] * 12, "target": [value * 0.5 for value in range(20, 44)]})
    result = run_baseline(frame, "target", "regression", seed=12)
    assert result.model_name == "RandomForestRegressor"
    assert set(result.metrics) == {"mae", "rmse", "r2"}
