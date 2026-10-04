"""Experiment E5: TCGA pan-cancer RNA-Seq tumour type (5 classes), classical vs. simulated quantum.

    python -m hcds.rnaseq --jobs 4

Data: UCI "gene expression cancer RNA-Seq" (BIO-003): 801 tumour samples x 20,531 genes from the TCGA PANCAN
HiSeq set, labelled BRCA, KIRC, COAD, LUAD or PRAD. The zip holds one .tar.gz with data.csv and labels.csv, joined on
the sample ID.

Protocol: 5-fold stratified CV (seed 42). In each fold, on the training part only: keep the ``--genes`` genes with the
highest variance, standardise, and (for the reduced view) fit PCA-8. Classical models (L2 logistic regression,
SVM-RBF, random forest) run on the variance-filtered genes and on the PCA-8 view. Quantum models see only PCA-8,
rescaled to [0, pi]: five one-vs-rest binary VQCs (angle encoding, 2 StronglyEntanglingLayers, class-weighted loss)
whose scores are normalised and arg-maxed, and a multi-class SVC on the IQP fidelity kernel (softmax of one-vs-rest
decision values). All on a noiseless statevector simulator; single-dataset results, not evidence of quantum advantage.
"""
from __future__ import annotations

import argparse
import io
import json
import tarfile
import time
import zipfile

import numpy as np
import pandas as pd
from scipy.special import softmax
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
                             precision_recall_fscore_support, roc_auc_score)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import SVC

from .benchmark import RESULTS_DIR, VariationalClassifier, environment, fidelity_kernel, iqp_states
from .experiments import raw_path

NAME = "E5_BIO-003_rnaseq"


class TopVariance(BaseEstimator, TransformerMixin):
    """Keep the ``k`` columns with the highest variance on the data it is fitted on."""

    def __init__(self, k: int = 2000) -> None:
        self.k = k

    def fit(self, x, y=None):
        self.columns_ = np.sort(np.argsort(np.asarray(x).var(axis=0))[::-1][:self.k])
        return self

    def transform(self, x):
        return np.asarray(x)[:, self.columns_]


def load_rnaseq() -> tuple[pd.DataFrame, pd.Series]:
    tables = {}
    with zipfile.ZipFile(raw_path("BIO-003")) as archive:
        member = next(m for m in archive.namelist() if m.endswith(".tar.gz"))
        with archive.open(member) as raw, tarfile.open(fileobj=raw, mode="r|gz") as inner:
            for item in inner:
                if item.isfile() and item.name.endswith(".csv"):
                    tables[item.name.rsplit("/", 1)[-1]] = pd.read_csv(io.BytesIO(inner.extractfile(item).read()),
                                                                       index_col=0)
    data, labels = tables["data.csv"], tables["labels.csv"]["Class"]
    if not data.index.equals(labels.index):
        raise ValueError("data.csv and labels.csv sample IDs differ")
    return data, labels


def multiclass_metrics(y_true, proba, classes) -> dict:
    pred = proba.argmax(axis=1)
    labels = list(range(len(classes)))
    _, sens, _, _ = precision_recall_fscore_support(y_true, pred, labels=labels, zero_division=0)
    out = {"accuracy": accuracy_score(y_true, pred), "balanced_accuracy": balanced_accuracy_score(y_true, pred),
           "macro_f1": f1_score(y_true, pred, average="macro", labels=labels, zero_division=0),
           "macro_roc_auc_ovr": roc_auc_score(y_true, proba, multi_class="ovr", labels=labels)}
    out.update({f"sensitivity_{c}": sens[i] for i, c in enumerate(classes)})
    out["confusion_matrix"] = json.dumps(confusion_matrix(y_true, pred, labels=labels).tolist())
    return out


def classical(seed: int) -> dict:
    return {"LogisticRegression_L2": LogisticRegression(max_iter=5000, random_state=seed),
            "SVM_RBF": SVC(probability=True, random_state=seed),
            "RandomForest": RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=1)}


def run_fold(x, y, tr, te, fold, classes, *, genes, qubits, epochs, seed) -> list[dict]:
    from sklearn.base import clone

    x_tr, x_te, y_tr, y_te = x[tr], x[te], y[tr], y[te]
    base = {"fold": fold, "n_train": len(tr), "n_test": len(te)}
    rows = []

    def record(model, view, family, proba, t_fit, t_pred):
        rows.append({**base, "model": model, "features": view, "family": family,
                     **multiclass_metrics(y_te, proba, classes), "train_s": t_fit, "infer_s": t_pred})

    views = {f"var{genes}": lambda: [("var", TopVariance(genes)), ("scale", StandardScaler())],
             f"pca{qubits}": lambda: [("var", TopVariance(genes)), ("scale", StandardScaler()),
                                      ("pca", PCA(n_components=qubits, random_state=seed))]}
    for view, steps in views.items():
        for name, model in classical(seed).items():
            pipe = Pipeline(steps() + [("model", clone(model))])
            t0 = time.perf_counter(); pipe.fit(x_tr, y_tr); t1 = time.perf_counter()
            proba = pipe.predict_proba(x_te); t2 = time.perf_counter()
            record(name, view, "classical", proba, t1 - t0, t2 - t1)

    q_view = f"pca{qubits}"
    angles = Pipeline(views[q_view]() + [("angles", MinMaxScaler(feature_range=(0.0, np.pi)))]).fit(x_tr)
    a_tr, a_te = angles.transform(x_tr), np.clip(angles.transform(x_te), 0, np.pi)

    t0 = time.perf_counter()
    s_tr = iqp_states(a_tr, qubits)
    qsvm = SVC(kernel="precomputed", decision_function_shape="ovr", random_state=seed).fit(fidelity_kernel(s_tr, s_tr), y_tr)
    t1 = time.perf_counter()
    decision = qsvm.decision_function(fidelity_kernel(iqp_states(a_te, qubits), s_tr))
    record("QSVM_IQP_fidelity_kernel", q_view, "quantum kernel (simulated)", softmax(decision, axis=1), t1 - t0,
           time.perf_counter() - t1)

    scores, t_fit, t_pred = [], 0.0, 0.0
    for c in range(len(classes)):
        vqc = VariationalClassifier(qubits, epochs=epochs, seed=seed + 10 * fold + c, class_weight="balanced")
        t0 = time.perf_counter(); vqc.fit(a_tr, (y_tr == c).astype(int)); t1 = time.perf_counter()
        scores.append(vqc.predict_proba1(a_te)); t_pred += time.perf_counter() - t1; t_fit += t1 - t0
    ovr = np.clip(np.column_stack(scores), 1e-9, None)
    record("VQC_angle_SEL2_one_vs_rest", q_view, "quantum (simulated)", ovr / ovr.sum(axis=1, keepdims=True),
           t_fit, t_pred)  # times summed over the binary VQCs
    return rows


def run(*, genes: int = 2000, qubits: int = 8, epochs: int = 30, folds: int = 5, seed: int = 42, jobs: int = 1,
        folds_limit: int | None = None) -> dict:
    from joblib import Parallel, delayed

    started = time.time()
    data, labels = load_rnaseq()
    classes = sorted(labels.unique())
    x, y = data.to_numpy(dtype=float), labels.map({c: i for i, c in enumerate(classes)}).to_numpy()
    splits = list(StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed).split(x, y))[:folds_limit]
    chunks = Parallel(n_jobs=jobs)(delayed(run_fold)(x, y, tr, te, fold, classes, genes=genes, qubits=qubits,
                                                     epochs=epochs, seed=seed) for fold, (tr, te) in enumerate(splits))
    results = pd.DataFrame([row for chunk in chunks for row in chunk])
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_DIR / f"{NAME}_folds.csv", index=False)
    metric_cols = [c for c in results.columns if c not in ("fold", "n_train", "n_test", "model", "features", "family",
                                                           "confusion_matrix")]
    agg = results.groupby(["features", "family", "model"])[metric_cols].agg(["mean", "std"])
    summary = pd.DataFrame(index=agg.index)
    for c in metric_cols:
        summary[c] = agg[(c, "mean")].map("{:.3f}".format) + " ± " + agg[(c, "std")].fillna(0).map("{:.3f}".format)
    summary.reset_index().to_csv(RESULTS_DIR / f"{NAME}_summary.csv", index=False)
    meta = {"experiment": "E5", "dataset_id": "BIO-003", "samples": int(len(y)), "genes_raw": int(x.shape[1]),
            "genes_all_zero": int((x.max(axis=0) == 0).sum()),
            "class_counts": {c: int((labels == c).sum()) for c in classes},
            "cv": f"StratifiedKFold, {folds} folds, seed {seed}" + (f", first {folds_limit} only" if folds_limit else ""),
            "preprocessing": f"in-fold top-{genes} variance genes, StandardScaler; reduced view PCA-{qubits}",
            "quantum_view": f"PCA-{qubits} rescaled to [0, pi] on the training fold",
            "vqc": f"{len(classes)} one-vs-rest binary VQCs (angle encoding, 2 StronglyEntanglingLayers, class-weighted "
                   f"BCE, Adam lr 0.05, batch 32, {epochs} epochs), scores normalised to sum to 1, argmax",
            "qsvm": "IQPEmbedding (2 repeats) exact fidelity kernel, multi-class SVC C=1, softmax of OvR decision values",
            "wall_clock_s": round(time.time() - started, 1), "parallel_jobs": jobs, "environment": environment()}
    (RESULTS_DIR / f"{NAME}_run.json").write_text(json.dumps(meta, indent=2))
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--genes", type=int, default=2000)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--folds-limit", type=int, help="Run only the first N folds (smoke tests)")
    args = parser.parse_args(argv)
    meta = run(genes=args.genes, epochs=args.epochs, jobs=args.jobs, folds_limit=args.folds_limit)
    print(json.dumps({k: meta[k] for k in ("samples", "class_counts", "wall_clock_s")}))
    print(pd.read_csv(RESULTS_DIR / f"{NAME}_summary.csv")[
        ["features", "model", "accuracy", "balanced_accuracy", "macro_f1", "macro_roc_auc_ovr", "train_s"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
