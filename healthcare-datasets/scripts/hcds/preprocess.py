"""Leakage-aware preprocessing for tabular datasets, plus the check that marks ``preprocessing_validated``.

Design rules (see documentation/preprocessing_guide.md):
- every fitted step (imputation, scaling, encoding, PCA, feature selection) lives inside a scikit-learn
  Pipeline so it is fitted on training folds only;
- splits are stratified for classification and grouped by patient/subject when a group column exists;
- no rows or labels are dropped silently: rows with a missing target are counted and reported.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, StandardScaler


@dataclass
class PreparedSplit:
    x_train: pd.DataFrame
    x_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series
    dropped_missing_target: int
    notes: list[str] = field(default_factory=list)


def tabular_preprocessor(features: pd.DataFrame, *, scale: str = "standard",
                         min_frequency: float | None = None) -> ColumnTransformer:
    """Median-impute + scale numeric columns; mode-impute + one-hot the rest.

    ``min_frequency`` pools categories rarer than that share of the training data into one infrequent column.
    """
    numeric = features.select_dtypes(include=["number", "bool"]).columns.tolist()
    categorical = [c for c in features.columns if c not in numeric]
    scaler = StandardScaler() if scale == "standard" else MinMaxScaler(feature_range=(0.0, np.pi))
    return ColumnTransformer([
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", scaler)]), numeric),
        ("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist" if min_frequency else "ignore",
                                     min_frequency=min_frequency, sparse_output=False)),
        ]), categorical),
    ])


def quantum_ready_pipeline(features: pd.DataFrame, n_qubits: int, min_frequency: float | None = None) -> Pipeline:
    """Impute/encode -> standardise -> PCA to ``n_qubits`` components -> rescale to [0, pi] for angle encoding.

    All steps are fitted on training data only when used inside cross-validation or fit on x_train.
    """
    return Pipeline([
        ("prep", tabular_preprocessor(features, scale="standard", min_frequency=min_frequency)),
        ("pca", PCA(n_components=n_qubits, random_state=0)),
        ("angles", MinMaxScaler(feature_range=(0.0, np.pi))),
    ])


def split(frame: pd.DataFrame, target: str, *, group: str | None = None, test_size: float = 0.25,
          seed: int = 42, task: str = "classification") -> PreparedSplit:
    missing = int(frame[target].isna().sum())
    clean = frame.dropna(subset=[target])
    notes = [f"{missing} rows without a target excluded (reported, not silently dropped)"] if missing else []
    x = clean.drop(columns=[target] + ([group] if group else []))
    y = clean[target]
    if group:
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train_idx, test_idx = next(splitter.split(x, y, groups=clean[group]))
        overlap = set(clean[group].iloc[train_idx]) & set(clean[group].iloc[test_idx])
        if overlap:
            raise AssertionError(f"Group leakage: {len(overlap)} groups in both splits")
        notes.append(f"grouped split on {group!r}: no subject appears in both train and test")
        return PreparedSplit(x.iloc[train_idx], x.iloc[test_idx], y.iloc[train_idx], y.iloc[test_idx], missing, notes)
    stratify = y if task == "classification" and y.value_counts().min() >= 2 else None
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=test_size, random_state=seed, stratify=stratify)
    if task == "classification":
        notes.append("stratified split" if stratify is not None else "unstratified split (a class has < 2 rows)")
    else:
        notes.append("random split (regression target)")
    return PreparedSplit(x_train, x_test, y_train, y_test, missing, notes)


def cv_splitter(y: pd.Series, groups: pd.Series | None = None, n_splits: int = 5, seed: int = 42):
    if groups is not None:
        return StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)


def validate_preprocessing(frame: pd.DataFrame, target: str, *, group: str | None = None, n_qubits: int = 4,
                           task: str = "classification", min_frequency: float | None = None) -> dict:
    """Run the pipeline end to end and assert the invariants that justify ``preprocessing_validated``."""
    prepared = split(frame, target, group=group, task=task)
    checks: dict[str, bool] = {}
    pipe = tabular_preprocessor(prepared.x_train, min_frequency=min_frequency).fit(prepared.x_train)
    train_t, test_t = pipe.transform(prepared.x_train), pipe.transform(prepared.x_test)
    checks["row_count_preserved"] = (
        train_t.shape[0] + test_t.shape[0] + prepared.dropped_missing_target == len(frame)
    )
    checks["no_nan_after_transform"] = not (np.isnan(train_t).any() or np.isnan(test_t).any())
    if task == "classification":
        checks["all_labels_present_in_train"] = set(prepared.y_test.unique()) <= set(prepared.y_train.unique())
    if prepared.x_train.select_dtypes(include=["number", "bool"]).shape[1]:
        # Standardised numeric columns have mean ~0 on the data the scaler was fitted on, i.e. train only.
        checks["scaler_fitted_on_train_only"] = bool(np.allclose(train_t[:, :1].mean(), 0.0, atol=1e-6))
    q = quantum_ready_pipeline(prepared.x_train, n_qubits, min_frequency=min_frequency).fit(prepared.x_train)
    angles = q.transform(prepared.x_test)
    checks["quantum_features_shape"] = angles.shape[1] == n_qubits
    checks["train_angles_within_0_pi"] = bool(
        (q.transform(prepared.x_train) >= -1e-9).all() and (q.transform(prepared.x_train) <= np.pi + 1e-9).all()
    )
    return {"ok": all(checks.values()), "checks": checks, "notes": prepared.notes,
            "train_rows": len(prepared.y_train), "test_rows": len(prepared.y_test)}
