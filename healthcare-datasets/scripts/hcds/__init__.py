"""Tooling for the healthcare dataset catalogue: schema, catalogue build, acquisition, validation, QML feasibility."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "catalog"
RECORDS_DIR = CATALOG_DIR / "records"
LOG_DIR = ROOT / "logs"
DATA_DIRS = (
    "medical_imaging",
    "clinical_tabular",
    "biomedical",
    "time_series",
    "public_health",
    "healthcare_nlp",
)
