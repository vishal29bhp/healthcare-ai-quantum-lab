# Preprocessing

The implementation is `scripts/hcds/preprocess.py`: leakage-aware tabular pipelines, grouped and stratified splits, the QML angle-encoding view, and `validate_preprocessing`, which backs the *Preprocessing validated* status. Per-modality rules are in `documentation/preprocessing_guide.md`. Write derived data to `<category>/<subcategory>/processed/`, which is git-ignored.
