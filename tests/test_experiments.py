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


def test_cross_validation_reports_mean_and_std_per_metric():
    frame = pd.DataFrame({"age": range(20, 44), "smoker": ["yes", "no"] * 12, "target": ["high", "low"] * 12})
    result = run_baseline(frame, "target", "classification", seed=12, cv_folds=4)
    assert result.cv_folds == 4
    assert set(result.cv_metrics) == {"accuracy_mean", "accuracy_std", "f1_weighted_mean", "f1_weighted_std"}
    regression = run_baseline(frame.assign(target=range(24)), "target", "regression", seed=12, cv_folds=3)
    assert regression.cv_metrics["mae_mean"] >= 0
    assert regression.cv_metrics["rmse_mean"] >= 0


def test_cross_validation_caps_folds_at_smallest_class_and_can_be_skipped():
    frame = pd.DataFrame({"x": range(12), "target": ["a"] * 9 + ["b"] * 3})
    result = run_baseline(frame, "target", "classification", cv_folds=5)
    assert result.cv_folds == 3
    assert "reduced from 5 to 3" in result.notes[0]
    assert run_baseline(frame, "target", "classification", cv_folds=0).cv_metrics == {}


def test_regression_folds_keep_two_rows_per_validation_fold():
    frame = pd.DataFrame({"x": range(10), "target": [value * 1.5 for value in range(10)]})
    result = run_baseline(frame, "target", "regression", cv_folds=10)
    assert result.cv_folds == 5
    assert all(value == value for value in result.cv_metrics.values())  # no NaN
