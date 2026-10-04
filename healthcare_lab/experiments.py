"""Reproducible classical ML baselines for tabular datasets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


@dataclass
class ExperimentResult:
    task: str
    model_name: str
    seed: int
    train_rows: int
    test_rows: int
    metrics: dict[str, float]
    cv_folds: int = 0
    cv_metrics: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def build_preprocessor(features: pd.DataFrame) -> ColumnTransformer:
    numeric = features.select_dtypes(include=["number", "bool"]).columns.tolist()
    categorical = [name for name in features.columns if name not in numeric]
    return ColumnTransformer(
        transformers=[
            ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median"))]), numeric),
            ("categorical", Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]), categorical),
        ],
        remainder="drop",
    )


CV_SCORERS = {
    "classification": {"accuracy": "accuracy", "f1_weighted": "f1_weighted"},
    "regression": {"mae": "neg_mean_absolute_error", "rmse": "neg_root_mean_squared_error", "r2": "r2"},
}


def run_baseline(frame: pd.DataFrame, target: str, task: str, seed: int = 42, cv_folds: int = 5) -> ExperimentResult:
    """Fit a random-forest baseline and return held-out and cross-validated metrics.

    The target is never imputed; rows with a missing target are excluded.
    Set ``cv_folds`` to 0 to skip cross-validation.
    """
    if target not in frame.columns:
        raise ValueError("Select a valid target column.")
    if task not in {"classification", "regression"}:
        raise ValueError("Task must be classification or regression.")
    clean = frame.dropna(subset=[target]).copy()
    if len(clean) < 10:
        raise ValueError("At least 10 rows with a target value are required.")
    features = clean.drop(columns=[target])
    if features.shape[1] == 0:
        raise ValueError("At least one feature column is required.")
    labels = clean[target]
    if task == "classification":
        if labels.nunique() < 2:
            raise ValueError("Classification needs at least two target classes.")
        counts = labels.value_counts()
        stratify = labels if counts.min() >= 2 else None
        estimator: Any = RandomForestClassifier(n_estimators=150, random_state=seed, n_jobs=-1)
    else:
        labels = pd.to_numeric(labels, errors="raise")
        stratify = None
        estimator = RandomForestRegressor(n_estimators=150, random_state=seed, n_jobs=-1)
    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.25, random_state=seed, stratify=stratify
    )
    pipeline = Pipeline([("preprocess", build_preprocessor(features)), ("model", estimator)])
    cv_metrics, folds_used, notes = cross_validate_pipeline(pipeline, features, labels, task, seed, cv_folds)
    pipeline.fit(x_train, y_train)
    prediction = pipeline.predict(x_test)
    if task == "classification":
        metrics = {
            "accuracy": float(accuracy_score(y_test, prediction)),
            "f1_weighted": float(f1_score(y_test, prediction, average="weighted", zero_division=0)),
        }
        model_name = "RandomForestClassifier"
    else:
        metrics = {
            "mae": float(mean_absolute_error(y_test, prediction)),
            "rmse": float(mean_squared_error(y_test, prediction) ** 0.5),
            "r2": float(r2_score(y_test, prediction)),
        }
        model_name = "RandomForestRegressor"
    return ExperimentResult(task, model_name, seed, len(x_train), len(x_test), metrics, folds_used, cv_metrics, notes)


def cross_validate_pipeline(
    pipeline: Pipeline, features: pd.DataFrame, labels: pd.Series, task: str, seed: int, folds: int
) -> tuple[dict[str, float], int, list[str]]:
    """Return mean/std k-fold metrics, the folds actually used, and any notes.

    Classification uses stratified folds, capped at the smallest class size;
    regression folds are capped so each validation fold has at least two rows.
    """
    if folds == 0:
        return {}, 0, []
    if folds < 2:
        raise ValueError("Cross-validation needs at least 2 folds (or 0 to skip).")
    if task == "classification":
        usable = min(folds, int(labels.value_counts().min()))
        splitter: Any = StratifiedKFold(n_splits=usable, shuffle=True, random_state=seed)
    else:
        # Every validation fold needs at least two rows, or R² is undefined (NaN).
        usable = min(folds, len(labels) // 2)
        splitter = KFold(n_splits=usable, shuffle=True, random_state=seed)
    if usable < 2:
        return {}, 0, ["Cross-validation skipped: not enough rows for 2 folds."]
    notes = [f"Cross-validation reduced from {folds} to {usable} folds to fit the data."] if usable < folds else []
    scorers = CV_SCORERS[task]
    scores = cross_validate(pipeline, features, labels, cv=splitter, scoring=scorers)
    cv_metrics: dict[str, float] = {}
    for name, scorer in scorers.items():
        values = scores[f"test_{name}"]
        if scorer.startswith("neg_"):
            values = -values
        cv_metrics[f"{name}_mean"] = float(values.mean())
        cv_metrics[f"{name}_std"] = float(values.std())
    return cv_metrics, usable, notes
