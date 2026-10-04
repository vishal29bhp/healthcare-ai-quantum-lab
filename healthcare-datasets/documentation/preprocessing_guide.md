# Preprocessing guide (Task 7)

Shared rules for every modality:
- keep an untouched copy of the source under `raw/` when the licence allows it;
- write derived data to `processed/` (git-ignored);
- record every decision in `parse_config.json` or the experiment's `_run.json`;
- never drop rows or labels silently. Counts are reported, as in `hcds.preprocess.split`.

## Tabular (implemented: `scripts/hcds/preprocess.py`)

| Step | Rule |
|---|---|
| Inspection | `hcds.validate.profile`: dtypes, missing cells per column, duplicate rows, class distribution |
| Leakage | Remove post-outcome variables (for example follow-up `time` in Heart Failure CLN-010) and identifiers. Split **by patient** (`group=`) whenever a patient can contribute several rows (CLN-003 encounters, MIMIC stays) |
| Splits | Stratified hold-out (`split`) or `StratifiedGroupKFold` (`cv_splitter`); fixed seeds |
| Imputation, encoding, scaling | Median or most-frequent imputation, one-hot encoding (`handle_unknown=ignore`) and standard scaling, all inside a `Pipeline`, so they are fitted on training folds only |
| Imbalance | Report PR-AUC and balanced accuracy; use class weights before resampling. Resample only inside training folds |
| QML view | `quantum_ready_pipeline`: preprocess → PCA(n_qubits) → MinMax to [0, π], fitted on training data |

`validate_preprocessing` is the check behind the *Preprocessing validated* status. It asserts that rows are conserved, that no NaN survives, that every test label is seen in training, that the scaler was fitted only on training data, and that the QML feature shape and angle range are right. CLN-009 passes these checks; see `logs/validation_log.csv`.

## Medical images (design; not executed in this batch)

- **Integrity.** Open every file (pydicom or nibabel for DICOM/NIfTI, Pillow for PNG/JPEG). Check modality tags, dimensions, bit depth, the image-to-label join and mask/image shape agreement.
- **Normalisation.** CT: clip Hounsfield units to a window. MRI: per-volume z-score or N4 bias correction. X-ray, dermoscopy and fundus: resize keeping the aspect ratio, then per-channel normalise.
- **Augmentation.** Use only label-preserving augmentation. Avoid flips where laterality matters, and avoid colour jitter that destroys dermoscopic cues.
- **Splits.** Split by patient or study (NIH ChestX-ray14, CheXpert, MIMIC-CXR and LIDC-IDRI have several images per patient), and keep the official test splits where they exist (PCam, MedMNIST, ISIC).

## Time-series (design)

- **Checks.** Validate the sampling frequency, channel names and units from the WFDB or EDF headers, and find missing intervals and flat-line segments.
- **Filtering.** ECG: 0.5–40 Hz band-pass. EEG: notch at the mains frequency plus a band-pass. PPG: 0.5–8 Hz.
- **Windows.** Use fixed-length windows (for example 10 s ECG, 30 s sleep epochs per the AASM/R&K annotations). Assign windows to splits **by subject or record**, never window-randomly. This matters most for MIT-BIH, where the inter-patient (de Chazal) split is standard.
- **Normalisation.** Use per-record z-score statistics computed within the training fold only.

## Biomedical and molecular (design)

- **Molecules.** Canonicalise SMILES (RDKit) and remove duplicates, keeping assay provenance. Use scaffold splits for property prediction and cold-drug or cold-target splits for DTI (DAVIS, KIBA) to avoid memorisation.
- **Sequences.** Check the alphabet and sequence-length distribution. Use k-mer or one-hot encodings, and use homology-aware (sequence-identity-clustered) splits for protein tasks.
- **Expression data.** Keep sample-to-patient mapping (TCGA barcodes), and fit any log transform or variance filter on training data only.

## Text (design)

- Record provenance, language and de-identification status for each corpus. MIMIC-IV-Note and MedNLI are de-identified but credentialed, so they never leave approved machines.
- Use minimal cleaning. Keep negations, units, dosages and section headers, which carry clinical meaning.
- Use the corpus's official splits (MedQA, PubMedQA, MedMCQA and BC5CDR all define them). Deduplicate questions across splits when combining sources.
