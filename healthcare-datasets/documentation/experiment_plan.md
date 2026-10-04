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
| E2 | CLN-002 Pima | binary | same four | VQC/QSVM at 8 qubits, no reduction | 5-fold stratified, repeated ×5 | **Run (simulator)**; results below |
| E3 | CLN-001 Heart Disease | binary (num>0) | same four | VQC/QSVM at 8 qubits after in-fold selection | repeated 5×5 CV | **Run (simulator)**; results below |
| E4 | CLN-003 Diabetes 130 | readmission | LR, HistGB | QSVM on a 2–5k stratified, patient-grouped subsample; VQC with mini-batches | StratifiedGroupKFold on patient | **Run (simulator)**; results below |
| E5 | BIO-003 RNA-Seq | 5-class | LR (L2), SVM, RF | Multi-class VQC (one-vs-rest) after variance filter + PCA-8 | 5-fold stratified | Not run: BIO-003 is not among the 15 approved downloads |
| E6 | IMG-018 MedMNIST (e.g. PneumoniaMNIST) | binary | ResNet-18 (official splits), LR on CNN embeddings | Hybrid: frozen CNN embedding → PCA-8 → VQC head | Official train/val/test | Not run: IMG-018 is not approved, and zenodo.org is blocked by the network policy |
| E7 | TS-001 MIT-BIH | beat classification (AAMI classes) | HistGB on RR/morphology features, 1D-CNN | Hybrid VQC on 8 engineered features | Inter-patient (DS1/DS2) | **Run (simulator)**; results below |

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

## Shared setup for E2–E4 (and E7)

Runner: `scripts/hcds/experiments.py` (E2–E4) and `scripts/hcds/ecg.py` (E7). Per-fold rows are in `experiments/results/<name>_folds.csv`, mean ± SD in `_summary.csv`, corrected t-tests in `_tests.csv`, and data notes, seeds and library versions in `_run.json`.

- Every fold fits imputation (median / most frequent), one-hot encoding, standardisation, the reduction step (PCA or `SelectKBest` on the F-score) and the [0, π] angle rescaling on its training part only.
- The quantum models are unchanged from E1 except for width: 8 qubits. The VQC uses angle (RY) encoding, 2 StronglyEntanglingLayers, ⟨Z₀⟩ readout, Adam (lr 0.05), batch 32 and 30 epochs. The QSVM is an SVC on an exact IQP-embedding fidelity kernel. Both run on PennyLane 0.45.1 `default.qubit`, noiseless with analytic expectations. IQP states are now computed directly with numpy; this matches PennyLane's `IQPEmbedding` to about 1e-15 (`tests/test_hcds_experiments.py`).
- The decision threshold is 0.5 for every model. No hyperparameter search was run for any model.
- "Significant" below means p < 0.05 on the Nadeau–Bengio corrected resampled t-test, with no correction for the number of comparisons. Each `_tests.csv` holds 4 to 20 comparisons, so treat p values near 0.05 as weak.
- Hardware: a 4-vCPU x86_64 cloud container, with folds run in parallel. Timings are per fold under that load.

## E2 results: CLN-002 Pima diabetes, 5-fold × 5 repeats, 8 qubits, no reduction

768 women, 268 positive. Zeros in glucose (5), blood pressure (35), skin thickness (227), insulin (374) and BMI (11) are physiologically impossible, so they were recoded as missing and median-imputed in-fold. All models see the same 8 features.

| Model | Balanced acc. | Sensitivity | Specificity | ROC-AUC | PR-AUC | Brier | Train s/fold |
|---|---|---|---|---|---|---|---|
| Logistic regression | 0.722 ± 0.030 | 0.566 ± 0.063 | 0.878 ± 0.036 | 0.836 ± 0.021 | 0.722 ± 0.044 | 0.157 | 0.02 |
| Random forest | 0.730 ± 0.035 | 0.616 ± 0.068 | 0.844 ± 0.032 | 0.830 ± 0.024 | 0.712 ± 0.048 | 0.159 | 1.1 |
| SVM-RBF | 0.700 ± 0.036 | 0.529 ± 0.062 | 0.870 ± 0.032 | 0.826 ± 0.024 | 0.714 ± 0.044 | 0.163 | 0.06 |
| HistGB | 0.713 ± 0.036 | 0.611 ± 0.068 | 0.816 ± 0.029 | 0.810 ± 0.030 | 0.677 ± 0.049 | 0.186 | 0.20 |
| VQC (simulated) | 0.661 ± 0.051 | 0.397 ± 0.124 | 0.925 ± 0.035 | 0.811 ± 0.030 | 0.707 ± 0.046 | 0.171 | 70.3 |
| QSVM (IQP, simulated) | 0.693 ± 0.042 | 0.561 ± 0.090 | 0.826 ± 0.043 | 0.796 ± 0.034 | 0.634 ± 0.054 | 0.174 | 0.11 |

- On ROC-AUC, the VQC (0.811) ties HistGB and is below logistic regression by 0.024 (p = 0.02). The QSVM is below logistic regression (−0.039, p = 0.015) and SVM-RBF (−0.030, p = 0.03). It is level with RF and HistGB.
- The VQC again ranks reasonably but sits on the wrong threshold: sensitivity is 0.40 against 0.57–0.62 for the classical models. Its balanced accuracy is below LR (p = 0.017) and RF (p = 0.018).

## E3 results: CLN-001 Heart Disease (Cleveland), 5-fold × 5 repeats, 8 of 13 features chosen in-fold

303 patients; target num > 0 (139 positive). `ca` has 4 missing values and `thal` has 2. cp, restecg, slope and thal are one-hot encoded, then `SelectKBest` keeps 8 encoded columns per fold.

| Model | Features | Balanced acc. | Sensitivity | Specificity | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|
| Logistic regression | all | 0.846 ± 0.047 | 0.797 ± 0.063 | 0.894 ± 0.059 | 0.911 ± 0.040 | 0.906 ± 0.046 | 0.117 |
| Logistic regression | select-8 | 0.848 ± 0.042 | 0.800 ± 0.067 | 0.896 ± 0.062 | 0.910 ± 0.038 | 0.907 ± 0.046 | 0.115 |
| SVM-RBF | select-8 | 0.832 ± 0.043 | 0.793 ± 0.065 | 0.872 ± 0.074 | 0.906 ± 0.038 | 0.905 ± 0.042 | 0.120 |
| Random forest | select-8 | 0.802 ± 0.042 | 0.775 ± 0.065 | 0.829 ± 0.076 | 0.888 ± 0.038 | 0.892 ± 0.037 | 0.135 |
| HistGB | select-8 | 0.797 ± 0.040 | 0.747 ± 0.067 | 0.848 ± 0.066 | 0.865 ± 0.040 | 0.869 ± 0.038 | 0.153 |
| QSVM (IQP, simulated) | select-8 | 0.763 ± 0.061 | 0.748 ± 0.079 | 0.777 ± 0.102 | 0.841 ± 0.061 | 0.827 ± 0.071 | 0.164 |
| VQC (simulated) | select-8 | 0.679 ± 0.059 | 0.610 ± 0.099 | 0.748 ± 0.100 | 0.721 ± 0.060 | 0.696 ± 0.065 | 0.214 |

All classical rows for all features are in `E3_CLN-001_heart_summary.csv`.

- Feature selection costs the classical models nothing here: logistic regression scores 0.910 on 8 features and 0.911 on all 13.
- On the same 8 features, the QSVM is below logistic regression (ROC-AUC −0.069, p = 0.008) and SVM-RBF (−0.065, p = 0.006). It is not distinguishable from HistGB (p = 0.34).
- The VQC is below every classical model on both metrics (all p < 0.002). Most selected columns are one-hot indicators, which give angle encoding only two values each. That is a plausible reason, but it was not tested.

## E4 results: CLN-003 Diabetes 130-US hospitals, 30-day readmission, StratifiedGroupKFold on patient (5 folds)

Of 101,766 encounters, 2,423 ended in death or hospice (disposition 11, 13, 14, 19, 20 or 21) and were removed, as in Strack et al. 2014. That leaves 99,343 encounters from 69,990 patients, 11,314 (11.4%) readmitted within 30 days. No patient appears in both the training and test sides of any fold; the runner asserts this. Weight (97% missing) and the identifiers were dropped. diag_1–3 were mapped to Strack et al.'s ICD-9 groups, and categories under 1% of a training fold are pooled. Because the classes are imbalanced, every model, quantum ones included, uses balanced class weights, so the 0.5 threshold is meaningful. The weighted QSVM is scored with sigmoid(decision value), because Platt scaling would undo the weighting. The quantum models train on a 3,000-encounter stratified subsample of each training fold and are tested on the whole test fold (about 20,000 encounters). LR and HistGB are also trained on that exact subsample.

| Model | Training rows | Features | Balanced acc. | Sensitivity | Specificity | ROC-AUC | PR-AUC | Train s/fold |
|---|---|---|---|---|---|---|---|---|
| HistGB | 79,474 | all | 0.622 ± 0.004 | 0.568 ± 0.014 | 0.677 ± 0.009 | 0.673 ± 0.005 | 0.229 ± 0.013 | 11 |
| Logistic regression | 79,474 | all | 0.616 ± 0.007 | 0.548 ± 0.013 | 0.684 ± 0.004 | 0.662 ± 0.005 | 0.213 ± 0.009 | 9 |
| HistGB | 79,474 | PCA-8 | 0.595 ± 0.006 | 0.555 ± 0.018 | 0.635 ± 0.014 | 0.637 ± 0.006 | 0.197 ± 0.006 | 8 |
| Logistic regression | 79,474 | PCA-8 | 0.594 ± 0.002 | 0.511 ± 0.004 | 0.677 ± 0.004 | 0.637 ± 0.005 | 0.196 ± 0.006 | 4 |
| Logistic regression | 3,000 | PCA-8 | 0.587 ± 0.009 | 0.508 ± 0.014 | 0.667 ± 0.016 | 0.624 ± 0.011 | 0.187 ± 0.014 | 0.2 |
| HistGB | 3,000 | PCA-8 | 0.533 ± 0.002 | 0.161 ± 0.011 | 0.905 ± 0.008 | 0.579 ± 0.009 | 0.152 ± 0.005 | 1.4 |
| VQC (simulated) | 3,000 | PCA-8 | 0.558 ± 0.013 | 0.540 ± 0.185 | 0.575 ± 0.178 | 0.592 ± 0.022 | 0.162 ± 0.010 | 294 |
| QSVM (IQP, simulated) | 3,000 | PCA-8 | 0.515 ± 0.010 | 0.196 ± 0.067 | 0.834 ± 0.054 | 0.545 ± 0.007 | 0.128 ± 0.004 | 1.3 |

- The task is hard for every model; results reported elsewhere for this table are typically ROC-AUC 0.65–0.70 (from memory, not re-checked here). Most of what is lost comes from compressing to 8 PCA components (0.673 → 0.637) and from training on 3,000 rows instead of about 79,000.
- With 5 folds and a 3,000-row training subsample tested on about 20,000 rows, the corrected t-test has very little power for the subsample comparisons: none of them reach p < 0.05, including LR vs. QSVM (ROC-AUC −0.079, p = 0.14). Against HistGB on all features with all rows, both quantum models are clearly worse (p < 0.01). The fair, same-data comparison stays inconclusive.
- The VQC's operating point swings from fold to fold (sensitivity SD 0.185). The class-weighted QSVM still under-calls positives (sensitivity 0.20).

## E5 and E6: not run

- **E5** (BIO-003, UCI gene-expression RNA-Seq) is hosted on archive.ics.uci.edu, which the network allows, but it was not among the 15 approved downloads. It needs `approved=yes` in `catalog/acquisition_plan.csv`.
- **E6** (IMG-018 MedMNIST) is not approved either, and zenodo.org is blocked by the network policy. It also needs a CNN and therefore a deep-learning library, which is not installed.

## E7 results: TS-001 MIT-BIH, AAMI N/S/V/F beats, inter-patient DS1 → DS2

The split follows de Chazal et al. (2004): train on the 22 DS1 records and test on the 22 DS2 records, so no patient is in both. The four paced records are excluded, and class Q is left unscored. That gives DS1 N/S/V/F = 45,824 / 943 / 3,788 / 414 beats and DS2 = 44,218 / 1,836 / 3,219 / 388. Beat positions come from the reference annotations. Eight features are taken from lead MLII after median-filter baseline removal: pre-RR, post-RR, local RR (mean of the previous 10), pre/local RR, post/pre RR, R amplitude, QRS width and QRS area. Those 8 are the quantum view. The "+wave24" view adds the beat waveform from −250 to +400 ms, decimated to 24 samples. Every model uses balanced class weights.

The quantum models train on 3 class-balanced draws from DS1, of up to 500 beats per class (1,914 beats, since F has only 414), and are scored on all of DS2. LR, SVM-RBF and HistGB are trained on exactly the same draws. The VQC is 4 one-vs-rest binary VQCs (8 qubits, the same circuit as above, class-weighted loss) whose scores are normalised and arg-maxed. The QSVM is a multi-class SVC on the IQP kernel. Rows with "all DS1" are single fits, so they have no SD.

| Model | Training beats | Features | Balanced acc. (macro sens.) | Macro F1 | Macro ROC-AUC | Sens. S | PPV S | Sens. V | PPV V | Train s |
|---|---|---|---|---|---|---|---|---|---|---|
| Logistic regression | all DS1 (50,969) | 8 | 0.861 | 0.596 | 0.962 | 0.837 | 0.338 | 0.858 | 0.926 | 0.9 |
| HistGB | all DS1 | 8 | 0.719 | 0.507 | 0.919 | 0.200 | 0.175 | 0.936 | 0.758 | 3.2 |
| HistGB | all DS1 | 8 + wave24 | 0.675 | 0.482 | 0.934 | 0.216 | 0.235 | 0.950 | 0.491 | 11 |
| MLP 64-32 (stands in for the 1D-CNN) | all DS1 | 8 + wave24 | 0.685 | 0.480 | 0.878 | 0.580 | 0.336 | 0.908 | 0.422 | 7.9 |
| Logistic regression | 1,914 balanced | 8 | 0.845 ± 0.016 | 0.585 ± 0.015 | 0.958 ± 0.006 | 0.784 ± 0.060 | 0.322 ± 0.029 | 0.852 ± 0.006 | 0.902 ± 0.033 | 0.03 |
| SVM-RBF | 1,914 balanced | 8 | 0.783 ± 0.024 | 0.541 ± 0.021 | 0.935 ± 0.003 | 0.530 ± 0.066 | 0.303 ± 0.024 | 0.949 ± 0.009 | 0.667 ± 0.069 | 0.3 |
| HistGB | 1,914 balanced | 8 | 0.751 ± 0.038 | 0.513 ± 0.037 | 0.921 ± 0.005 | 0.383 ± 0.145 | 0.230 ± 0.066 | 0.916 ± 0.003 | 0.735 ± 0.083 | 1.5 |
| VQC one-vs-rest (simulated) | 1,914 balanced | 8 | 0.688 ± 0.061 | 0.464 ± 0.040 | 0.907 ± 0.021 | 0.334 ± 0.200 | 0.127 ± 0.088 | 0.856 ± 0.082 | 0.677 ± 0.082 | 841 (4 VQCs) |
| QSVM (IQP, simulated) | 1,914 balanced | 8 | 0.625 ± 0.004 | 0.444 ± 0.036 | 0.820 ± 0.021 | 0.214 ± 0.016 | 0.158 ± 0.016 | 0.941 ± 0.014 | 0.539 ± 0.146 | 0.6 |

Per-class sensitivity and PPV for N and F, plus the confusion matrices, are in `E7_TS-001_mitbih_runs.csv`.

- Simple RR-interval features with a linear model carry most of the inter-patient signal (S sensitivity 0.84). Flexible models such as HistGB and the MLP overfit to the training patients and lose S beats, which is the usual inter-patient failure.
- On identical 8-feature training draws, both quantum models trail logistic regression and SVM-RBF on every macro metric. The VQC varies a lot between draws (S sensitivity 0.16–0.55).
- Deviations from the plan: an MLP replaces the 1D-CNN because no deep-learning library is installed, and with one fixed split there are no folds for the corrected t-test, so draw-to-draw SD is the only spread reported.

## Overall reading (E1–E4, E7)

On five clinical datasets, with matched features and training rows, the simulated 8-qubit VQC and IQP-kernel QSVM never beat the best classical model. Where the comparison has power (E2, E3, E7), they are usually measurably worse, and in a few pairings they are level with RF or HistGB. This is one ansatz, one feature map, no tuning, noiseless simulation and fixed thresholds. It says nothing for or against quantum advantage in general. It does say that these off-the-shelf circuits are not competitive baselines on small clinical tables.

## Reproduce

```bash
pip install -r healthcare-datasets/requirements-qml.txt      # PennyLane, wfdb
cd healthcare-datasets/scripts
python -m hcds.acquire                                       # the 15 approved open files (raw/ is git-ignored)
python -m hcds.validate                                      # checksums, SHA256SUMS.txt members, parsing
python -m hcds.benchmark --dataset-id CLN-009 --name CLN-009_wdbc --folds 5 --qubits 4 --vqc-epochs 30   # E1
python -m hcds.experiments E2 E3 E4 --jobs 4                 # about 10, 4 and 12 minutes on 3-4 vCPUs
OMP_NUM_THREADS=1 python -m hcds.ecg --jobs 3 --cache /tmp/mitbih_beats.csv   # E7, about 20 minutes
python -m hcds.build_catalog
```
