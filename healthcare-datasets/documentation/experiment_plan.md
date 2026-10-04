# Classical-versus-quantum experimental plan (Task 9)

## Principles

- All models on a dataset share **identical outer folds**: `StratifiedKFold`, or `StratifiedGroupKFold` when patients repeat, with seed 42.
- Every fitted transform lives inside the fold.
- Classical models run on the full feature set **and** on the same reduced features the quantum models see. A gap between the two views is then attributed to the features, not to the model family.
- Metrics: accuracy, balanced accuracy, precision, sensitivity, specificity, F1, ROC-AUC, PR-AUC, Brier score (calibration) and per-fold confusion matrices. Survival tasks use the C-index or integrated Brier score. Segmentation uses Dice or HD95. Regression uses MAE, RMSE and R².
- Report mean ± SD across folds, wall-clock training and inference time, hardware, library versions, the simulator and shot settings, and seeds. Treat differences inside fold SD as no difference. Use a corrected resampled t-test (Nadeau–Bengio) before claiming one.

## Planned experiments

| ID | Dataset | Task | Classical baselines | Quantum / hybrid | Split | Status |
|---|---|---|---|---|---|---|
| E1 | CLN-009 WDBC | binary | LR, SVM-RBF, RF, HistGB (all features and PCA-4) | VQC (angle + 2-layer StronglyEntangling), QSVM (IQP fidelity kernel), 4 qubits | 5-fold stratified | **Run (simulator)**; results below |
| E2 | CLN-002 Pima | binary | same four | VQC/QSVM at 8 qubits, no reduction | 5-fold stratified, repeated ×5 | Ready; waiting on download approval and network |
| E3 | CLN-001 Heart Disease | binary (num>0) | same four | VQC/QSVM at 8 qubits after in-fold selection | repeated 5×5 CV | Ready; waiting on download |
| E4 | CLN-003 Diabetes 130 | readmission | LR, HistGB | QSVM on a 2–5k stratified, patient-grouped subsample; VQC with mini-batches | StratifiedGroupKFold on patient | Waiting on download |
| E5 | BIO-003 RNA-Seq | 5-class | LR (L2), SVM, RF | Multi-class VQC (one-vs-rest) after variance filter + PCA-8 | 5-fold stratified | Waiting on download |
| E6 | IMG-018 MedMNIST (e.g. PneumoniaMNIST) | binary | ResNet-18 (official splits), LR on CNN embeddings | Hybrid: frozen CNN embedding → PCA-8 → VQC head | Official train/val/test | Waiting on download |
| E7 | TS-001 MIT-BIH | beat classification (AAMI classes) | HistGB on RR/morphology features, 1D-CNN | Hybrid VQC on 8 engineered features | Inter-patient (DS1/DS2) | Waiting on download |

## E1 results: CLN-009, 5-fold CV, seed 42, malignant = positive class

Source: `experiments/results/CLN-009_wdbc_summary.csv`, per-fold rows in `_folds.csv`, environment in `_run.json`. These are measured on the scikit-learn bundled copy of WDBC: 569 rows, 30 features, 212 positive. The VQC was trained for 30 epochs; the QSVM used an exact statevector kernel on PennyLane `default.qubit` (noiseless) on an x86_64 CPU, with a total wall-clock of 66.7 s.

| Model | Features | Balanced acc. | Sensitivity | Specificity | ROC-AUC | PR-AUC | Brier | Train s/fold |
|---|---|---|---|---|---|---|---|---|
| Logistic regression | all 30 | 0.968 ± 0.026 | 0.944 ± 0.059 | 0.992 ± 0.013 | 0.995 ± 0.006 | 0.994 ± 0.006 | 0.020 | 0.04 |
| SVM-RBF | all 30 | 0.965 ± 0.025 | 0.958 ± 0.042 | 0.972 ± 0.026 | 0.995 ± 0.007 | 0.993 ± 0.008 | 0.022 | 0.01 |
| Logistic regression | PCA-4 | 0.960 ± 0.029 | 0.939 ± 0.063 | 0.980 ± 0.024 | 0.994 ± 0.006 | 0.993 ± 0.006 | 0.029 | 0.03 |
| SVM-RBF | PCA-4 | 0.954 ± 0.021 | 0.939 ± 0.046 | 0.969 ± 0.030 | 0.992 ± 0.007 | 0.988 ± 0.009 | 0.033 | 0.01 |
| QSVM (IQP kernel, simulated) | PCA-4 | 0.919 ± 0.023 | 0.897 ± 0.088 | 0.941 ± 0.052 | 0.978 ± 0.009 | 0.961 ± 0.023 | 0.058 | 1.41 |
| VQC (simulated) | PCA-4 | 0.774 ± 0.051 | 0.548 ± 0.103 | 1.000 ± 0.000 | 0.976 ± 0.010 | 0.968 ± 0.013 | 0.118 | 9.93 |

What this shows, and what it does not:

- On this dataset and at this size, the simulated quantum models **did not outperform** classical models on the same 4 PCA features.
- The VQC ranks cases well (ROC-AUC 0.976), but its fixed 0.5 threshold on a ⟨Z⟩-based score is badly calibrated: sensitivity is 0.55 and the Brier score is 0.118. Threshold tuning or Platt scaling inside the training folds would be the fair next step. It was not done here.
- Only one ansatz, one encoding, 4 qubits, 30 epochs and one seed were tried. No hyperparameter search was run for any model, and the result is noiseless with analytic expectations. No conclusion about quantum advantage, positive or negative, follows from this.

## Reproduce

```bash
pip install -r healthcare-datasets/requirements-qml.txt
cd healthcare-datasets/scripts
python -m hcds.pipeline                                      # acquires the approved CLN-009 mirror and validates it
python -m hcds.benchmark --dataset-id CLN-009 --name CLN-009_wdbc --folds 5 --qubits 4 --vqc-epochs 30
python -m hcds.benchmark --data my.csv --target y --name mydata --classical-only   # any other CSV
```
