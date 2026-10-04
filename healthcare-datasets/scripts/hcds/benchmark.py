"""Classical vs. quantum (simulated) benchmark on a locally acquired tabular dataset.

Every model sees the same stratified outer folds. Within each fold all preprocessing (scaling, PCA, angle
rescaling) is fitted on the training part only. Classical models run on the full feature set and on the same
PCA-reduced features the quantum models get, so the comparison isolates the model rather than the features.

Quantum models run on PennyLane's noiseless ``default.qubit`` statevector simulator (optional dependency, see
requirements-qml.txt). Results are simulator results on one small dataset: they are not evidence of quantum
advantage and should not be read as such.
"""
from __future__ import annotations

import argparse
import warnings
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score, brier_score_loss,
                             confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import SVC

from . import ROOT

RESULTS_DIR = ROOT / "experiments" / "results"
# SVC(probability=True) is deprecated in scikit-learn 1.9 but still supported; it is needed for the precomputed
# quantum kernel, where CalibratedClassifierCV cannot re-split a kernel matrix.
warnings.filterwarnings("ignore", message=".*probability.*deprecated", category=FutureWarning)


def metrics(y_true, y_pred, y_score) -> dict[str, float]:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall_sensitivity": recall_score(y_true, y_pred, zero_division=0),
        "specificity": tn / (tn + fp) if (tn + fp) else float("nan"),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_score),
        "pr_auc": average_precision_score(y_true, y_score),
        "brier": brier_score_loss(y_true, np.clip(y_score, 0, 1)),
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
    }


def classical_models(seed: int, class_weight: str | None = None) -> dict:
    return {
        "LogisticRegression": LogisticRegression(max_iter=5000, random_state=seed, class_weight=class_weight),
        "SVM_RBF": SVC(kernel="rbf", probability=True, random_state=seed, class_weight=class_weight),
        "RandomForest": RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1, class_weight=class_weight),
        "HistGradientBoosting": HistGradientBoostingClassifier(random_state=seed, class_weight=class_weight),
    }


def angle_pipeline(n_qubits: int, seed: int) -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("pca", PCA(n_components=n_qubits, random_state=seed)),
                     ("angles", MinMaxScaler(feature_range=(0.0, np.pi)))])


class VariationalClassifier:
    """Angle-encoded (RY) data, StronglyEntanglingLayers ansatz, <Z0> readout mapped to P(y=1). Adam, minibatches."""

    def __init__(self, n_qubits: int, n_layers: int = 2, epochs: int = 30, batch: int = 32, lr: float = 0.05,
                 seed: int = 0, class_weight: str | None = None) -> None:
        import pennylane as qml
        from pennylane import numpy as pnp

        self.qml, self.pnp = qml, pnp
        self.n_qubits, self.n_layers, self.epochs, self.batch, self.lr, self.seed = n_qubits, n_layers, epochs, batch, lr, seed
        self.class_weight = class_weight  # "balanced": weight each class by n / (2 * n_class), as scikit-learn does
        dev = qml.device("default.qubit", wires=n_qubits)

        @qml.qnode(dev)
        def circuit(weights, x):
            qml.AngleEmbedding(x, wires=range(n_qubits), rotation="Y")
            qml.StronglyEntanglingLayers(weights, wires=range(n_qubits))
            return qml.expval(qml.PauliZ(0))

        self.circuit = circuit

    def _proba(self, weights, bias, x):
        return (1 - (self.circuit(weights, x) + bias)) / 2  # expval in [-1, 1] -> probability-like score

    def fit(self, x, y):
        pnp = self.pnp
        rng = np.random.default_rng(self.seed)
        shape = self.qml.StronglyEntanglingLayers.shape(n_layers=self.n_layers, n_wires=self.n_qubits)
        weights = pnp.array(rng.normal(0, 0.1, size=shape), requires_grad=True)
        bias = pnp.array(0.0, requires_grad=True)
        opt = self.qml.AdamOptimizer(self.lr)
        x = pnp.array(x, requires_grad=False)
        y = pnp.array(y.astype(float), requires_grad=False)

        pos = float(y.mean()) if self.class_weight == "balanced" else 0.5
        w_pos, w_neg = 0.5 / pos, 0.5 / (1 - pos)

        def loss(w, b, xb, yb):
            p = pnp.clip(self._proba(w, b, xb), 1e-6, 1 - 1e-6)
            return -pnp.mean(w_pos * yb * pnp.log(p) + w_neg * (1 - yb) * pnp.log(1 - p))

        for _ in range(self.epochs):
            order = rng.permutation(len(y))
            for start in range(0, len(y), self.batch):
                idx = order[start:start + self.batch]
                weights, bias, _, _ = opt.step(loss, weights, bias, x[idx], y[idx])
        self.weights_, self.bias_ = weights, bias
        return self

    def predict_proba1(self, x):
        return np.asarray(self._proba(self.weights_, self.bias_, self.pnp.array(x)), dtype=float)


def iqp_states_pennylane(x: np.ndarray, n_qubits: int) -> np.ndarray:
    """Statevectors of PennyLane's IQPEmbedding (n_repeats=2), one circuit per sample. Reference for iqp_states."""
    import pennylane as qml

    dev = qml.device("default.qubit", wires=n_qubits)

    @qml.qnode(dev)
    def state(sample):
        qml.IQPEmbedding(sample, wires=range(n_qubits), n_repeats=2)
        return qml.state()

    return np.stack([np.asarray(state(sample)) for sample in x])


def _walsh_hadamard(states: np.ndarray) -> np.ndarray:
    """Apply H on every qubit to a batch of statevectors (rows), in O(n 2^n) per state."""
    out, h, dim = states.copy(), 1, states.shape[1]
    while h < dim:
        out = out.reshape(len(states), -1, 2, h)
        out = np.stack([out[:, :, 0] + out[:, :, 1], out[:, :, 0] - out[:, :, 1]], axis=2)
        h *= 2
    return out.reshape(len(states), dim) / np.sqrt(dim)


def iqp_states(x: np.ndarray, n_qubits: int, n_repeats: int = 2) -> np.ndarray:
    """Exact statevectors of PennyLane's IQPEmbedding, computed directly with numpy.

    Each repeat is H on all wires, RZ(x_i) on wire i, then MultiRZ(x_i x_j) on every pair: all diagonal after the
    Hadamards, so one repeat is a phase vector times a Walsh-Hadamard transform. Wire 0 is the most significant bit,
    as in PennyLane. Matches ``iqp_states_pennylane`` to ~1e-15 (see tests) and is far faster for large batches.
    """
    x = np.asarray(x, dtype=float)
    dim = 2 ** n_qubits
    z = 1 - 2 * ((np.arange(dim)[:, None] >> (n_qubits - 1 - np.arange(n_qubits))) & 1)  # (dim, n) in {+1, -1}
    i, j = np.triu_indices(n_qubits, k=1)
    phase = x @ z.T + (x[:, i] * x[:, j]) @ (z[:, i] * z[:, j]).T  # (samples, dim)
    diag = np.exp(-0.5j * phase)
    states = np.full((len(x), dim), dim ** -0.5, dtype=complex) * diag
    for _ in range(n_repeats - 1):
        states = diag * _walsh_hadamard(states)
    return states


def fidelity_kernel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.abs(a.conj() @ b.T) ** 2


def run(data: pd.DataFrame, target: str, *, n_qubits: int = 4, folds: int = 5, seed: int = 42,
        vqc_epochs: int = 30, include_quantum: bool = True) -> pd.DataFrame:
    x_all = data.drop(columns=[target]).to_numpy(dtype=float)
    y_all = data[target].to_numpy(dtype=int)
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    rows = []
    for fold, (tr, te) in enumerate(cv.split(x_all, y_all)):
        x_tr, x_te, y_tr, y_te = x_all[tr], x_all[te], y_all[tr], y_all[te]
        for name, model in classical_models(seed).items():
            for features in ("all", f"pca{n_qubits}"):
                steps = [("scale", StandardScaler())]
                if features != "all":
                    steps.append(("pca", PCA(n_components=n_qubits, random_state=seed)))
                pipe = Pipeline(steps + [("model", clone(model))])
                t0 = time.perf_counter(); pipe.fit(x_tr, y_tr); t1 = time.perf_counter()
                score = pipe.predict_proba(x_te)[:, 1]; t2 = time.perf_counter()
                rows.append({"fold": fold, "model": name, "features": features, "family": "classical",
                             **metrics(y_te, (score >= 0.5).astype(int), score),
                             "train_s": t1 - t0, "infer_s": t2 - t1})
        if not include_quantum:
            continue
        prep = angle_pipeline(n_qubits, seed).fit(x_tr)
        q_tr, q_te = prep.transform(x_tr), np.clip(prep.transform(x_te), 0, np.pi)
        vqc = VariationalClassifier(n_qubits, epochs=vqc_epochs, seed=seed + fold)
        t0 = time.perf_counter(); vqc.fit(q_tr, y_tr); t1 = time.perf_counter()
        score = vqc.predict_proba1(q_te); t2 = time.perf_counter()
        rows.append({"fold": fold, "model": "VQC_angle_SEL2", "features": f"pca{n_qubits}", "family": "quantum (simulated)",
                     **metrics(y_te, (score >= 0.5).astype(int), score), "train_s": t1 - t0, "infer_s": t2 - t1})
        t0 = time.perf_counter()
        s_tr, s_te = iqp_states(q_tr, n_qubits), iqp_states(q_te, n_qubits)
        qsvm = SVC(kernel="precomputed", probability=True, random_state=seed).fit(fidelity_kernel(s_tr, s_tr), y_tr)
        t1 = time.perf_counter()
        score = qsvm.predict_proba(fidelity_kernel(s_te, s_tr))[:, 1]; t2 = time.perf_counter()
        rows.append({"fold": fold, "model": "QSVM_IQP_fidelity_kernel", "features": f"pca{n_qubits}",
                     "family": "quantum kernel (simulated)", **metrics(y_te, (score >= 0.5).astype(int), score),
                     "train_s": t1 - t0, "infer_s": t2 - t1})
    return pd.DataFrame(rows)


def summarise(results: pd.DataFrame) -> pd.DataFrame:
    keys = ["family", "model", "features"]
    cols = ["accuracy", "balanced_accuracy", "recall_sensitivity", "specificity", "f1", "roc_auc", "pr_auc", "brier",
            "train_s", "infer_s"]
    agg = results.groupby(keys)[cols].agg(["mean", "std"])
    out = pd.DataFrame(index=agg.index)
    for c in cols:
        out[c] = agg[(c, "mean")].map("{:.3f}".format) + " ± " + agg[(c, "std")].map("{:.3f}".format)
    return out.reset_index()


def load_acquired(dataset_id: str) -> tuple[pd.DataFrame, str]:
    """Load a successfully acquired file and binarise its target so the configured positive class is 1."""
    from .acquire import MANIFEST_PATH
    from .status import read_csv_rows
    from .validate import PARSE_CONFIG, read_tabular

    cfg = json.loads(PARSE_CONFIG.read_text())[dataset_id]
    rows = [r for r in read_csv_rows(MANIFEST_PATH) if r["dataset_id"] == dataset_id and r["download_status"] == "success"
            and cfg.get("file") in (None, r["requested_files"])]
    if not rows:
        raise SystemExit(f"{dataset_id} has no successful acquisition in the manifest; run hcds.pipeline first")
    frame = read_tabular(ROOT / rows[-1]["local_path"], **cfg.get("read_options", {}))
    target = cfg["target"]
    frame["label_positive"] = (frame.pop(target) == cfg.get("positive_label", 1)).astype(int)
    return frame, "label_positive"


def environment() -> dict:
    env = {"python": platform.python_version(), "platform": platform.platform(), "processor": platform.processor(),
           "numpy": np.__version__, "pandas": pd.__version__, "scikit-learn": sklearn.__version__}
    try:
        import pennylane as qml
        env["pennylane"] = qml.__version__
        env["quantum_device"] = "default.qubit (noiseless statevector simulator, analytic expectation values)"
    except ImportError:
        env["pennylane"] = "not installed"
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset-id", help="Use the acquired file for this ID (manifest + catalog/parse_config.json)")
    source.add_argument("--data", type=Path, help="CSV with numeric features and a 0/1 target")
    parser.add_argument("--target", help="Target column (required with --data)")
    parser.add_argument("--name", required=True, help="Results file stem, e.g. CLN-009_breast_cancer")
    parser.add_argument("--qubits", type=int, default=4)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--vqc-epochs", type=int, default=30)
    parser.add_argument("--classical-only", action="store_true")
    args = parser.parse_args(argv)
    if args.dataset_id:
        data, target = load_acquired(args.dataset_id)
    else:
        if not args.target:
            parser.error("--target is required with --data")
        data, target = pd.read_csv(args.data), args.target
    args.target = target
    started = time.time()
    results = run(data, args.target, n_qubits=args.qubits, folds=args.folds, seed=args.seed,
                  vqc_epochs=args.vqc_epochs, include_quantum=not args.classical_only)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_DIR / f"{args.name}_folds.csv", index=False)
    summary = summarise(results)
    summary.to_csv(RESULTS_DIR / f"{args.name}_summary.csv", index=False)
    meta = {"dataset": args.name, "rows": int(len(data)), "features": int(data.shape[1] - 1),
            "class_counts": {str(k): int(v) for k, v in data[args.target].value_counts().items()},
            "folds": args.folds, "seed": args.seed, "qubits": args.qubits, "vqc_epochs": args.vqc_epochs,
            "wall_clock_s": round(time.time() - started, 1), "environment": environment()}
    (RESULTS_DIR / f"{args.name}_run.json").write_text(json.dumps(meta, indent=2))
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
