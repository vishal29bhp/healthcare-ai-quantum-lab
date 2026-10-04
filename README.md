# Healthcare AI & Quantum Research Lab

An initial, local-first vertical slice for exploring tabular healthcare research datasets. It profiles files, runs reproducible classical machine-learning baselines, and records metadata-only experiment history in SQLite.

> **Privacy warning:** Do **not** upload identifiable patient data or protected health information (PHI). This prototype is not a clinical system and is not designed for regulated production workloads.

## What is implemented

- CSV, TSV, XLSX, and XLS uploads, validated by extension and a 20 MB size limit.
- In-memory dataset profiling: dimensions, missing values, duplicate rows, data types, and descriptive statistics.
- Random-forest classification and regression baselines with median/most-frequent imputation, categorical one-hot encoding, reproducible train/test splits, configurable seed, and held-out metrics.
- A local SQLite experiment registry containing timestamp, dataset SHA-256 fingerprint, dimensions, target, model, seed, split sizes, metrics, and software versions. Raw uploads are not written to the registry or disk.
- A synthetic, non-patient sample dataset in `sample_data/`.

## How to run

### Prerequisites

- Python 3.10 or newer (the Docker image uses 3.12)
- Git
- Free disk space for the datasets you download. The four large PhysioNet ECG/EEG sets alone are about 5 GB.

### 1. Set up the environment

```bash
git clone https://github.com/vishal29bhp/healthcare-ai-quantum-lab.git
cd healthcare-ai-quantum-lab

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

To run the quantum models and the ECG experiment, also install PennyLane and wfdb:

```bash
pip install -r healthcare-datasets/requirements-qml.txt
```

### 2. Start the Streamlit app

```bash
streamlit run app.py
```

Open the URL that Streamlit prints (normally <http://localhost:8501>).

| Page | What it does |
|---|---|
| **Home** (`app.py`) | Upload a CSV, TSV, XLSX or XLS file (max 20 MB), profile it, and train a random-forest baseline. Try `sample_data/synthetic_patient_outcomes.csv` with target `risk_label` (classification) or `length_of_stay` (regression). |
| **Dataset Explorer** (`pages/1_Dataset_Explorer.py`) | Browse the 117-dataset catalogue by category, status and access level, and preview downloaded files. It appears in the sidebar once PR #4 is merged. |

Stop the app with `Ctrl+C`.

### 3. Build the healthcare dataset catalogue

All dataset commands run from `healthcare-datasets/scripts`:

```bash
cd healthcare-datasets/scripts
```

| Step | Command | What it does |
|---|---|---|
| Check metadata | `python -m hcds.build_catalog --check` | Validates all 117 records in `catalog/records/` |
| Preview downloads | `python -m hcds.pipeline --dry-run` | Lists what would be downloaded; fetches and writes nothing |
| Download and validate | `python -m hcds.pipeline` | Downloads every approved open dataset, verifies checksums, parses and preprocesses, then rebuilds the catalogue |
| One dataset only | `python -m hcds.pipeline --ids CLN-001` | Same, for the IDs given |
| Rebuild outputs | `python -m hcds.build_catalog` | Regenerates `catalog/master_catalog.csv` / `.xlsx`, category views and reports |

Raw files go into `<category>/<subcategory>/raw/<ID>/` and are git-ignored, so a fresh clone must re-run the pipeline before the experiments. Only datasets marked `approved=yes` in `catalog/acquisition_plan.csv` are fetched. Registration, credentialed and DUA datasets are never downloaded automatically; `catalog/access_restrictions.csv` lists their access steps.

### 4. Run the classical vs. quantum experiments

Each experiment needs its dataset downloaded first (step 3). Results are written to `healthcare-datasets/experiments/results/`.

| Experiment | Dataset | Command |
|---|---|---|
| E1 | CLN-009 Breast Cancer Wisconsin | `python -m hcds.benchmark --dataset-id CLN-009 --name CLN-009_wdbc --folds 5 --qubits 4` |
| E2, E3, E4 | CLN-002 Pima, CLN-001 Heart Disease, CLN-003 Diabetes readmission | `python -m hcds.experiments E2 E3 E4 --jobs 4` |
| E5 | BIO-003 TCGA RNA-Seq | `python -m hcds.rnaseq --jobs 4` |
| E7 | TS-001 MIT-BIH Arrhythmia | `OMP_NUM_THREADS=1 python -m hcds.ecg --jobs 4` |

Add `--classical-only` to E1-E4 to skip the (slow) simulated quantum models. The write-up of every result is in `healthcare-datasets/documentation/experiment_plan.md`.

### 5. Run the tests

From the repository root:

```bash
pytest -q
```

This runs the app tests and the offline dataset-toolkit tests; no network access is needed.

### 6. Run with Docker (app only)

```bash
docker build -t healthcare-ai-quantum-lab .
docker run --rm -p 8501:8501 healthcare-ai-quantum-lab
```

Then open <http://localhost:8501>. The local SQLite file created by the app is ignored by Git. Mount a private, encrypted volume if you need to keep it.

### Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: healthcare_lab` when running tests | Run `pytest` from the repository root, where `pyproject.toml` sets the import path |
| `... has no successful acquisition in the manifest` | Download that dataset first: `python -m hcds.pipeline --ids <ID>` |
| HTTP 403 or "Host not in allowlist" during downloads | Your network or proxy blocks that data host; the manifest records it and other datasets continue |
| E7 seems stuck | Set `OMP_NUM_THREADS=1` as shown above |
| PhysioNet downloads are slow | PhysioNet throttles each connection (about 160 KB/s); the multi-GB sets take hours |

## Guided deployment plan (manual; not performed by this repository)

1. Complete privacy, security, clinical-governance, and legal review; do not expose the prototype to PHI until approved.
2. Deploy the Docker image only to an approved private environment with TLS, authentication, network controls, encryption, retention/deletion policies, logging, and a managed secrets system.
3. Replace the local SQLite registry with an approved managed database and restrict access according to organizational policy.
4. Add threat modeling, dependency scanning, monitoring, backups, and incident-response procedures before any real-world use.
5. Validate model performance, fairness, calibration, and clinical workflow impact independently; this app is research tooling, not medical advice or a diagnostic device.

## QML research status

**Implemented:** classical scikit-learn baselines (logistic regression, SVM, random forest, gradient boosting) and simulated quantum models in PennyLane: a variational quantum classifier and an IQP-kernel quantum SVM. These were run on breast cancer, diabetes, heart disease, readmission, cancer RNA-Seq and ECG data (experiments E1 to E5 and E7).

**Result so far:** classical models matched or beat the simulated quantum models on every dataset. No quantum advantage is claimed. See `healthcare-datasets/documentation/experiment_plan.md`.

**Not implemented:** real quantum hardware runs and noise-aware evaluation.

## Limitations

- The app reads files into process memory and only checks extension/size; it is not a malware scanner or a secure PHI platform.
- It runs one baseline estimator per task and does not supply feature attribution, cross-validation, model persistence, authentication, or clinical validation.
- Excel parsing requires the included `openpyxl` dependency and may not support every legacy workbook feature.
