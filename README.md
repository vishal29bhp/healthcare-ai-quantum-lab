# Healthcare AI & Quantum Research Lab

An initial, local-first vertical slice for exploring tabular healthcare research datasets. It profiles files, runs reproducible classical machine-learning baselines, and records metadata-only experiment history in SQLite.

> **Privacy warning:** Do **not** upload identifiable patient data or protected health information (PHI). This prototype is not a clinical system and is not designed for regulated production workloads.

## What is implemented

- CSV, TSV, XLSX, and XLS uploads, validated by extension and a 20 MB size limit.
- In-memory dataset profiling: dimensions, missing values, duplicate rows, data types, and descriptive statistics.
- Random-forest classification and regression baselines with median/most-frequent imputation, categorical one-hot encoding, reproducible train/test splits, configurable seed, and held-out metrics.
- Data checks before training: duplicate rows, missing targets, mostly-missing, constant, and identifier-like columns, and possible target leakage (a feature identical to the target, correlated with it at |r| ≥ 0.95, or a low-cardinality feature that determines it exactly).
- Configurable k-fold cross-validation (default 5 folds, stratified for classification and capped at the smallest class size) reported as mean and standard deviation next to the held-out metrics.
- A local SQLite experiment registry containing timestamp, dataset SHA-256 fingerprint, dimensions, target, model, seed, split sizes, held-out and `cv_`-prefixed cross-validation metrics, and software versions. Raw uploads are not written to the registry or disk.
- A synthetic, non-patient sample dataset in `sample_data/`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements-dev.txt
streamlit run app.py
```

Then open the local URL printed by Streamlit and upload `sample_data/synthetic_patient_outcomes.csv`. Select `risk_label` for classification or `length_of_stay` for regression.

## Test

```bash
pytest -q
```

## Docker

```bash
docker build -t healthcare-ai-quantum-lab .
docker run --rm -p 8501:8501 healthcare-ai-quantum-lab
```

The local SQLite file created by the app is ignored by Git. Mount a private, encrypted volume if you need to retain it.

## Guided deployment plan (manual; not performed by this repository)

1. Complete privacy, security, clinical-governance, and legal review; do not expose the prototype to PHI until approved.
2. Deploy the Docker image only to an approved private environment with TLS, authentication, network controls, encryption, retention/deletion policies, logging, and a managed secrets system.
3. Replace the local SQLite registry with an approved managed database and restrict access according to organizational policy.
4. Add threat modeling, dependency scanning, monitoring, backups, and incident-response procedures before any real-world use.
5. Validate model performance, fairness, calibration, and clinical workflow impact independently; this app is research tooling, not medical advice or a diagnostic device.

## QML research status

**Implemented:** classical scikit-learn random-forest baselines.

**Planned (not implemented):** quantum feature maps, variational quantum classifiers, hybrid optimization, simulator/hardware benchmarks, and noise-aware evaluation. This repository makes no quantum experiment or quantum advantage claim.

## Limitations

- The app reads files into process memory and only checks extension/size; it is not a malware scanner or a secure PHI platform.
- It runs one baseline estimator per task and does not supply feature attribution, hyperparameter search, model persistence, authentication, or clinical validation.
- Data checks are heuristics: they can miss leakage and can flag legitimately strong predictors, so review each warning.
- Excel parsing requires the included `openpyxl` dependency and may not support every legacy workbook feature.
