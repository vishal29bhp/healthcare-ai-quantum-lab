# Implementation Plan

## Slice 1 — implemented

1. Provide safe, in-memory CSV/TSV/Excel ingestion with file extension and size checks.
2. Profile tabular datasets and show a preview in Streamlit.
3. Run reproducible, held-out classical classification and regression baselines with preprocessing.
4. Record only experiment metadata, metrics, software versions, and a dataset fingerprint in local SQLite.
5. Add synthetic data, automated tests, container instructions, and continuous integration.

## Slice 2 — implemented

1. Data checks for duplicates, missing targets, high missingness, constant and identifier-like columns, and possible target leakage.
2. Configurable k-fold cross-validation reported alongside the held-out split and recorded in the registry.

## Next research increments — planned

1. Add model comparison, calibration/fairness evaluation, and explainability after governance review.
2. Introduce a quantum simulator research track with documented classical baselines and noise-aware methodology.
3. Consider hardware experiments only after reproducibility, cost, privacy, and governance requirements are defined.

No quantum experiment is implemented in Slices 1 or 2, and this plan does not imply quantum advantage.
