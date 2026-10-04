# Feature engineering

Reduction for QML (PCA or selection to the target number of qubits, fitted in-fold) lives in `hcds.preprocess.quantum_ready_pipeline`. The planned per-modality extractors are CNN embeddings for images, HRV and spectral features for signals, fingerprints for molecules and sentence embeddings for text; they are described in `documentation/preprocessing_guide.md` and `documentation/qml_feasibility.md`. None is implemented yet.
