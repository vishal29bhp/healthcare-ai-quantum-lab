"""SQLite experiment registry that stores metadata only, never raw datasets."""
from __future__ import annotations

import json
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import sklearn

from .experiments import ExperimentResult


def software_versions() -> dict[str, str]:
    return {"python": platform.python_version(), "pandas": pd.__version__, "scikit_learn": sklearn.__version__}


def initialize_registry(path: str | Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                dataset_fingerprint TEXT NOT NULL,
                dataset_rows INTEGER NOT NULL,
                dataset_columns INTEGER NOT NULL,
                target_column TEXT NOT NULL,
                task TEXT NOT NULL,
                model_name TEXT NOT NULL,
                random_seed INTEGER NOT NULL,
                train_rows INTEGER NOT NULL,
                test_rows INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                versions_json TEXT NOT NULL
            )
        """)


def record_experiment(path: str | Path, fingerprint: str, rows: int, columns: int, target: str, result: ExperimentResult) -> None:
    initialize_registry(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """INSERT INTO experiments (created_at, dataset_fingerprint, dataset_rows, dataset_columns,
               target_column, task, model_name, random_seed, train_rows, test_rows, metrics_json, versions_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), fingerprint, rows, columns, target, result.task,
             result.model_name, result.seed, result.train_rows, result.test_rows,
             json.dumps(_all_metrics(result)), json.dumps(software_versions())),
        )


def _all_metrics(result: ExperimentResult) -> dict[str, float]:
    """Held-out metrics plus cross-validation metrics under a ``cv_`` prefix."""
    metrics = dict(result.metrics)
    if result.cv_folds:
        metrics["cv_folds"] = result.cv_folds
        metrics.update({f"cv_{name}": value for name, value in result.cv_metrics.items()})
    return metrics
