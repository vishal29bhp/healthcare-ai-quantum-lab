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
from sklearn.impute import SimpleImputer
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


def classical_models(seed: int) -> dict:
    return {
        "LogisticRegression": LogisticRegression(max_iter=5000, random_state=seed),
        "SVM_RBF": SVC(kernel="rbf", probability=True, random_state=seed),
        "RandomForest": RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1),
        "HistGradientBoosting": HistGradientBoostingClassifier(random_state=seed),
    }


def angle_pipeline(n_qubits: int, seed: int) -> Pipeline:
    return Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()),
                     ("pca", PCA(n_components=n_qubits, random_state=seed)),
                     ("angles", MinMaxScaler(feature_range=(0.0, np.pi)))])


class VariationalClassifier:
    """Angle-encoded (RY) data, StronglyEntanglingLayers ansatz, <Z0> readout mapped to P(y=1). Adam, minibatches."""

    def __init__(self, n_qubits: int, n_layers: int = 2, epochs: int = 30, batch: int = 32, lr: float = 0.05,
                 seed: int = 0) -> None:
        import pennylane as qml
        from pennylane import numpy as pnp

        self.qml, self.pnp = qml, pnp
        self.n_qubits, self.n_layers, self.epochs, self.batch, self.lr, self.seed = n_qubits, n_layers, epochs, batch, lr, seed
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

        def loss(w, b, xb, yb):
            p = pnp.clip(self._proba(w, b, xb), 1e-6, 1 - 1e-6)
            return -pnp.mean(yb * pnp.log(p) + (1 - yb) * pnp.log(1 - p))

        for _ in range(self.epochs):
            order = rng.permutation(len(y))
            for start in range(0, len(y), self.batch):
                idx = order[start:start + self.batch]
                weights, bias, _, _ = opt.step(loss, weights, bias, x[idx], y[idx])
        self.weights_, self.bias_ = weights, bias
        return self

    def predict_proba1(self, x):
        return np.asarray(self._proba(self.weights_, self.bias_, self.pnp.array(x)), dtype=float)


def iqp_states(x: np.ndarray, n_qubits: int) -> np.ndarray:
    """Statevectors of an IQP (ZZ-type) feature map, computed once per sample for an exact fidelity kernel."""
    import pennylane as qml

    dev = qml.device("default.qubit", wires=n_qubits)

    @qml.qnode(dev)
    def state(sample):
        qml.IQPEmbedding(sample, wires=range(n_qubits), n_repeats=2)
        return qml.state()

    return np.stack([np.asarray(state(sample)) for sample in x])


def fidelity_kernel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.abs(a.conj() @ b.T) ** 2


def run(data: pd.DataFrame, target: str, *, n_qubits: int = 4, folds: int = 5, seed: int = 42,
        vqc_epochs: int = 30, include_quantum: bool = True, repeats: int = 1) -> pd.DataFrame:
    """Repeated stratified K-fold; repeat r reshuffles with seed + r. Missing values are imputed inside each fold."""
    x_all = data.drop(columns=[target]).to_numpy(dtype=float)
    y_all = data[target].to_numpy(dtype=int)
    splits = [(r, fold, tr, te) for r in range(repeats)
              for fold, (tr, te) in enumerate(StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed + r)
                                              .split(x_all, y_all))]
    rows = []
    for repeat, fold, tr, te in splits:
        fold_rows_start = len(rows)
        x_tr, x_te, y_tr, y_te = x_all[tr], x_all[te], y_all[tr], y_all[te]
        for name, model in classical_models(seed).items():
            for features in ("all", f"pca{n_qubits}"):
                steps = [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
                if features != "all":
                    steps.append(("pca", PCA(n_components=n_qubits, random_state=seed)))
                pipe = Pipeline(steps + [("model", clone(model))])
                t0 = time.perf_counter(); pipe.fit(x_tr, y_tr); t1 = time.perf_counter()
                score = pipe.predict_proba(x_te)[:, 1]; t2 = time.perf_counter()
                rows.append({"fold": fold, "model": name, "features": features, "family": "classical",
                             **metrics(y_te, (score >= 0.5).astype(int), score),
                             "train_s": t1 - t0, "infer_s": t2 - t1})
        if not include_quantum:
            for row in rows[fold_rows_start:]:
                row["repeat"] = repeat
            continue
        prep = angle_pipeline(n_qubits, seed).fit(x_tr)
        q_tr, q_te = prep.transform(x_tr), np.clip(prep.transform(x_te), 0, np.pi)
        vqc = VariationalClassifier(n_qubits, epochs=vqc_epochs, seed=seed + 100 * repeat + fold)
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
        for row in rows[fold_rows_start:]:
            row["repeat"] = repeat
    return pd.DataFrame(rows)


def corrected_ttest(diffs: np.ndarray, n_train: int, n_test: int) -> tuple[float, float]:
    """Nadeau-Bengio corrected resampled t-test on per-fold score differences. Returns (t, two-sided p)."""
    from scipy import stats

    k = len(diffs)
    var = np.var(diffs, ddof=1)
    if k < 2 or var == 0:
        return float("nan"), float("nan")
    t = np.mean(diffs) / np.sqrt((1 / k + n_test / n_train) * var)
    return float(t), float(2 * stats.t.sf(abs(t), df=k - 1))


def compare(results: pd.DataFrame, n_rows: int, folds: int, reference: tuple[str, str],
            metrics_: tuple[str, ...] = ("balanced_accuracy", "roc_auc")) -> pd.DataFrame:
    """Every model vs. ``reference`` (model, features) on matched folds, with the corrected t-test."""
    n_test = n_rows / folds
    ref = results[(results.model == reference[0]) & (results.features == reference[1])].set_index(["repeat", "fold"])
    out = []
    for (model, features), group in results.groupby(["model", "features"]):
        if (model, features) == reference:
            continue
        group = group.set_index(["repeat", "fold"])
        for metric in metrics_:
            diffs = (group[metric] - ref.loc[group.index, metric]).to_numpy(dtype=float)
            t, p = corrected_ttest(diffs, n_rows - n_test, n_test)
            out.append({"model": model, "features": features, "reference": f"{reference[0]} ({reference[1]})",
                        "metric": metric, "mean_diff": round(float(np.mean(diffs)), 4), "t": round(t, 3),
                        "p_corrected": round(p, 4), "significant_at_0.05": bool(p < 0.05) if p == p else False})
    return pd.DataFrame(out)


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
    from .validate import PARSE_CONFIG, file_config, read_tabular

    config = json.loads(PARSE_CONFIG.read_text())
    wanted = config[dataset_id].get("benchmark_file")
    rows = [r for r in read_csv_rows(MANIFEST_PATH) if r["dataset_id"] == dataset_id and r["download_status"] == "success"
            and (wanted is None or r["requested_files"] == wanted)]
    if not rows:
        raise SystemExit(f"{dataset_id} has no successful acquisition in the manifest; run hcds.pipeline first")
    path = ROOT / rows[-1]["local_path"]
    cfg = file_config(config, dataset_id, path.name)
    frame = read_tabular(path, **cfg.get("read_options", {}))
    frame = frame.drop(columns=[c for c in cfg.get("drop_columns", []) if c in frame.columns])
    labels = frame.pop(cfg["target"])
    rule = cfg.get("positive_rule")
    if rule:  # e.g. {"op": "gt", "value": 0} for Heart Disease num > 0
        positive = {"gt": labels > rule["value"], "ge": labels >= rule["value"]}[rule["op"]]
    else:
        positive = labels == cfg.get("positive_label", 1)
    frame["label_positive"] = positive.astype(int)
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
    parser.add_argument("--repeats", type=int, default=1, help="Repeated K-fold: number of reshuffled repeats")
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
                  vqc_epochs=args.vqc_epochs, include_quantum=not args.classical_only, repeats=args.repeats)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_DIR / f"{args.name}_folds.csv", index=False)
    summary = summarise(results)
    summary.to_csv(RESULTS_DIR / f"{args.name}_summary.csv", index=False)
    if args.repeats * args.folds >= 2:
        compare(results, len(data), args.folds, ("LogisticRegression", f"pca{args.qubits}")).to_csv(
            RESULTS_DIR / f"{args.name}_comparisons.csv", index=False)
    meta = {"dataset": args.name, "rows": int(len(data)), "features": int(data.shape[1] - 1),
            "class_counts": {str(k): int(v) for k, v in data[args.target].value_counts().items()},
            "folds": args.folds, "repeats": args.repeats, "seed": args.seed, "qubits": args.qubits, "vqc_epochs": args.vqc_epochs,
            "wall_clock_s": round(time.time() - started, 1), "environment": environment()}
    (RESULTS_DIR / f"{args.name}_run.json").write_text(json.dumps(meta, indent=2))
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
