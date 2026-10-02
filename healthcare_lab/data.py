"""Safe data loading and dataset profiling helpers."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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
