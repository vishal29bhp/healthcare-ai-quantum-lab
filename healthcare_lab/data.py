"""Safe data loading and dataset profiling helpers."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
HIGH_MISSING_FRACTION = 0.5
LEAKAGE_CORRELATION = 0.95


def validate_upload(filename: str, size: int, max_bytes: int = MAX_UPLOAD_BYTES) -> str:
    """Validate an upload name and size without storing the upload on disk."""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only CSV, TSV, XLSX, and XLS files are supported.")
    if size <= 0:
        raise ValueError("The uploaded file is empty.")
    if size > max_bytes:
        raise ValueError(f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit.")
    return extension


def load_dataset(upload: BinaryIO, filename: str) -> pd.DataFrame:
    """Read a validated tabular upload into memory; callers must not persist it."""
    content = upload.read()
    extension = validate_upload(filename, len(content))
    buffer = BytesIO(content)
    if extension == ".csv":
        return pd.read_csv(buffer)
    if extension == ".tsv":
        return pd.read_csv(buffer, sep="\t")
    return pd.read_excel(buffer)


def fingerprint_dataset(frame: pd.DataFrame) -> str:
    """Return a stable SHA-256 fingerprint without saving the source data."""
    payload = frame.to_csv(index=False).encode("utf-8")
    return sha256(payload).hexdigest()


def profile_dataset(frame: pd.DataFrame) -> dict:
    """Compute compact, serializable descriptive statistics for a dataframe."""
    return {
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "missing_values": {column: int(count) for column, count in frame.isna().sum().items()},
        "duplicate_rows": int(frame.duplicated().sum()),
        "data_types": {column: str(dtype) for column, dtype in frame.dtypes.items()},
        "summary_statistics": frame.describe(include="all").fillna("").to_dict(),
    }


def check_dataset(frame: pd.DataFrame, target: str) -> list[str]:
    """Flag common data-quality and leakage problems before training a baseline.

    Returns human-readable warnings; an empty list means nothing was flagged.
    """
    warnings: list[str] = []
    rows = len(frame)
    if rows == 0:
        return ["The dataset has no rows."]
    duplicates = int(frame.duplicated().sum())
    if duplicates:
        warnings.append(f"{duplicates} duplicate row(s) may land in both train and test splits.")
    if target in frame.columns:
        missing_target = int(frame[target].isna().sum())
        if missing_target:
            warnings.append(f"Target `{target}` is missing in {missing_target} row(s); those rows are excluded.")
    labels = frame[target] if target in frame.columns else None
    for column in frame.columns:
        if column == target:
            continue
        values = frame[column]
        non_null = values.dropna()
        missing_fraction = 1 - len(non_null) / rows
        if missing_fraction > HIGH_MISSING_FRACTION:
            warnings.append(f"`{column}` is {missing_fraction:.0%} missing.")
        if non_null.nunique() <= 1:
            warnings.append(f"`{column}` is constant and carries no signal.")
            continue
        if _looks_like_identifier(column, non_null, rows):
            warnings.append(f"`{column}` looks like an identifier; consider dropping it before training.")
            continue
        if labels is not None:
            leak = _leakage_reason(values, labels, rows)
            if leak:
                warnings.append(f"Possible target leakage: `{column}` {leak}.")
    return warnings


def _looks_like_identifier(column: str, non_null: pd.Series, rows: int) -> bool:
    name = column.strip().lower()
    named_like_id = name == "id" or name.endswith(("_id", " id")) or name in {"mrn", "patient_id", "record_id", "uuid"}
    if named_like_id:
        return True
    if non_null.nunique() != rows or rows < 10:
        return False
    if pd.api.types.is_object_dtype(non_null) or pd.api.types.is_string_dtype(non_null):
        return True
    # Unique integers are only ID-like when they form a running sequence (1, 2, 3, ...).
    if pd.api.types.is_integer_dtype(non_null) and not pd.api.types.is_bool_dtype(non_null):
        ordered = non_null.sort_values()
        return bool((ordered.diff().dropna() == 1).all())
    return False


def _leakage_reason(values: pd.Series, labels: pd.Series, rows: int) -> str | None:
    paired = pd.DataFrame({"feature": values, "target": labels}).dropna()
    if len(paired) < 2:
        return None
    if paired["feature"].astype(str).equals(paired["target"].astype(str)):
        return "is identical to the target"
    numeric = pd.api.types.is_numeric_dtype(paired["feature"]) and pd.api.types.is_numeric_dtype(paired["target"])
    if numeric and paired["feature"].nunique() > 1 and paired["target"].nunique() > 1:
        correlation = paired["feature"].corr(paired["target"])
        if abs(correlation) >= LEAKAGE_CORRELATION:
            return f"has correlation {correlation:.2f} with the target"
    few_levels = paired["feature"].nunique() <= rows / 2
    if few_levels and paired["target"].nunique() > 1 and (paired.groupby("feature")["target"].nunique() == 1).all():
        return "determines the target exactly"
    return None
