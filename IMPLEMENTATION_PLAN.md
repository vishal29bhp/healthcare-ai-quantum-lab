# Implementation Plan

## Slice 1 — implemented

1. Provide safe, in-memory CSV/TSV/Excel ingestion with file extension and size checks.
2. Profile tabular datasets and show a preview in Streamlit.
3. Run reproducible, held-out classical classification and regression baselines with preprocessing.
4. Record only experiment metadata, metrics, software versions, and a dataset fingerprint in local SQLite.
5. Add synthetic data, automated tests, container instructions, and continuous integration.

## Next research increments — planned

1. Add schema checks, richer data-quality reports, and configurable cross-validation.
2. Add model comparison, calibration/fairness evaluation, and explainability after governance review.
3. Introduce a quantum simulator research track with documented classical baselines and noise-aware methodology.
4. Consider hardware experiments only after reproducibility, cost, privacy, and governance requirements are defined.

No quantum experiment is implemented in Slice 1, and this plan does not imply quantum advantage.
