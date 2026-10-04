# Quantum-encoding feasibility (Task 8)

The matrix is in `catalog/qml_feasibility_matrix.csv`, with one row for each of the 16 datasets that have a defined tabular view and a known size. Qualitative QML suitability for all 117 datasets is in the *QML Suitability* column of the master catalogue. **Nothing here claims quantum advantage.** These are resource estimates for planning simulator experiments.

## Estimation rules (`scripts/hcds/qml.py`)

| Quantity | Formula | Note |
|---|---|---|
| Angle encoding | 1 qubit per reduced feature (default target 8; 4 for CLN-009) | Shallow, hardware-friendly |
| Amplitude encoding | ⌈log₂ d⌉ qubits for d raw features | Generic state preparation needs about 2ⁿ − n − 1 CNOTs per sample, so it is only practical for small d. For BIO-003 (20,531 genes) that is 15 qubits but tens of thousands of CNOTs per sample |
| Basis encoding | bits × features | Suits binary symptom questionnaires (CLN-005) and one-hot sequence windows |
| ZZ/IQP feature map | d(d−1)/2 two-qubit entanglers per repetition | Used for fidelity kernels |
| QSVM kernel cost | about n_train²/2 kernel circuit evaluations | Capped at 2 M evaluations (about 2,000 training samples) for simulator planning |
| Simulator tier | ≤16 qubits: CPU statevector; ≤30: high-memory/GPU; above that, reduce further | Planning thresholds, not hard limits |

## Summary by dataset group *[assessment]*

| Group | Datasets | Verdict |
|---|---|---|
| Small clean tabular | CLN-001, 002, 005, 006, 007, 009, 010, 017; BIO-002 | **High** for simulator studies. 8–30 features reduce to 4–8 qubits with little information loss. The QSVM kernel is tractable on the full training set. Very small n means confidence intervals must be reported |
| Large tabular | CLN-003, CLN-004 | **Medium.** Needs a stratified (and, for CLN-003, patient-grouped) representative subsample of about 2–5k for kernels. Variational models can train on more with mini-batches |
| High-dimensional omics | BIO-003, BIO-001 | **Medium.** In-fold variance filtering then PCA-8. Amplitude encoding is worth studying only for its state-preparation cost |
| Imaging, time-series, text | most IMG, TS and NLP rows | **Low directly.** Hybrid only: a classical feature extractor (CNN embedding, HRV/spectral features, sentence embedding), then PCA to 8 qubits, then a VQC head. Compare against the same extractor with a logistic-regression head |
| Aggregate public health | PH-* | **Low.** Few independent samples; QML adds little beyond toy regression |

## Trainability and cost notes

- Use shallow, hardware-efficient ansätze (2–3 layers) at 4–8 qubits. Deeper or global-cost circuits risk barren plateaus.
- Hardware runs add shot noise and gate errors. Run on noiseless simulators first, then noisy simulators with realistic noise models, and only then on hardware, and report the shot counts.
- The angle range [0, π] comes from a MinMax scaler fitted on training data. Test values outside that range are clipped, and the clipping is documented.
