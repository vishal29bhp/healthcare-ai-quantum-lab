"""Experiments E2-E4 from documentation/experiment_plan.md: classical vs. simulated quantum on clinical tables.

    python -m hcds.experiments E2 E3 E4 --jobs 4

Each experiment loads its acquired raw file, then runs every model on identical outer folds
(``StratifiedKFold``, or ``StratifiedGroupKFold`` on the patient when patients repeat), repeated with different
shuffles where the plan says so. All fitted steps (imputation, encoding, scaling, PCA or feature selection, angle
rescaling) are fitted on the training part of each fold only.

Views: classical models run on all features and on the same ``qubits``-wide view the quantum models see. When the
quantum models train on a subsample (E4), the classical models are also run on that exact subsample, so the
comparison isolates the model family. Quantum models are the VQC and IQP-kernel QSVM from ``hcds.benchmark`` on a
noiseless statevector simulator. Differences are tested with the Nadeau-Bengio corrected resampled t-test.
These are simulator results on single datasets, not evidence for or against quantum advantage.

E7 (MIT-BIH beats) lives in ``hcds.ecg`` because it uses a fixed inter-patient split rather than CV.
"""
from __future__ import annotations

import argparse
import json
import time
import zipfile
from dataclasses import dataclass, field
from itertools import product

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import expit
from sklearn.base import clone
from sklearn.decomposition import PCA
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler
from sklearn.svm import SVC

from . import ROOT
from .acquire import MANIFEST_PATH
from .benchmark import (RESULTS_DIR, VariationalClassifier, classical_models, environment, fidelity_kernel,
                        iqp_states, metrics)
from .preprocess import tabular_preprocessor
from .status import read_csv_rows
from .validate import read_tabular


@dataclass
class Spec:
    experiment: str
    dataset_id: str
    name: str
    qubits: int = 8
    reduction: str = "pca"  # "pca", "select" (in-fold SelectKBest on F-score) or "none" (needs exactly `qubits` columns)
    folds: int = 5
    repeats: int = 1
    classical: tuple[str, ...] = ("LogisticRegression", "SVM_RBF", "RandomForest", "HistGradientBoosting")
    quantum_train_max: int | None = None  # stratified subsample of each training fold for the quantum models
    vqc_epochs: int = 30
    min_frequency: float | None = None  # rare categories pooled by OneHotEncoder, decided in-fold
    class_weight: str | None = None  # "balanced" reweights every model's loss, so a 0.5 threshold is meaningful
    notes: list[str] = field(default_factory=list)


SPECS = {
    "E2": Spec("E2", "CLN-002", "E2_CLN-002_pima", reduction="none", repeats=5),
    "E3": Spec("E3", "CLN-001", "E3_CLN-001_heart", reduction="select", repeats=5),
    "E4": Spec("E4", "CLN-003", "E4_CLN-003_readmission", reduction="pca", repeats=1,
               classical=("LogisticRegression", "HistGradientBoosting"), quantum_train_max=3000, min_frequency=0.01,
               class_weight="balanced"),
}


# ----------------------------------------------------------------------------------------------- data loading
def raw_path(dataset_id: str):
    rows = [r for r in read_csv_rows(MANIFEST_PATH) if r["dataset_id"] == dataset_id and r["download_status"] == "success"]
    if not rows:
        raise SystemExit(f"{dataset_id} has no successful acquisition in the manifest; run hcds.acquire first")
    path = ROOT / rows[-1]["local_path"]
    if not path.exists():
        raise SystemExit(f"{path} is listed in the manifest but missing on disk; raw files are not kept in git")
    return path


def load_pima() -> tuple[pd.DataFrame, np.ndarray, None, list[str]]:
    frame = read_tabular(raw_path("CLN-002"))
    y = (frame.pop("class") == "tested_positive").to_numpy(dtype=int)
    impossible = ["plas", "pres", "skin", "insu", "mass"]  # a zero here is a missing measurement, not a value
    zeros = {c: int((frame[c] == 0).sum()) for c in impossible}
    frame[impossible] = frame[impossible].replace(0, np.nan)
    notes = [f"zeros recoded as missing (median-imputed in-fold): {zeros}"]
    return frame, y, None, notes


def load_heart() -> tuple[pd.DataFrame, np.ndarray, None, list[str]]:
    frame = read_tabular(raw_path("CLN-001"), sep=",")
    y = (frame.pop("num") > 0).to_numpy(dtype=int)
    for column in ("cp", "restecg", "slope", "thal"):  # coded categories, one-hot encoded in-fold
        frame[column] = frame[column].map(lambda v: "missing" if pd.isna(v) else str(int(v)))
    notes = ["target = num > 0 (any angiographic disease)", "ca has 4 missing values (median-imputed in-fold); "
             "thal's 2 missing values are their own category", "cp, restecg, slope, thal one-hot encoded"]
    return frame, y, None, notes


ICD9_GROUPS = [  # Strack et al. 2014 (doi:10.1155/2014/781670), Table 2
    ("circulatory", [(390, 460), (785, 786)]), ("respiratory", [(460, 520), (786, 787)]),
    ("digestive", [(520, 580), (787, 788)]), ("injury", [(800, 1000)]), ("musculoskeletal", [(710, 740)]),
    ("genitourinary", [(580, 630), (788, 789)]), ("neoplasms", [(140, 240)]),
]


def icd9_group(code) -> str:
    if pd.isna(code):
        return "missing"
    code = str(code)
    if code[0] in "VE":
        return "other"
    value = float(code)
    if int(value) == 250:
        return "diabetes"
    for group, ranges in ICD9_GROUPS:
        if any(lo <= value < hi for lo, hi in ranges):
            return group
    return "other"


def load_readmission() -> tuple[pd.DataFrame, np.ndarray, np.ndarray, list[str]]:
    with zipfile.ZipFile(raw_path("CLN-003")) as archive, archive.open("diabetic_data.csv") as handle:
        # keep_default_na=False: "None" in max_glu_serum / A1Cresult means "not measured", a real category
        frame = pd.read_csv(handle, na_values=["?"], keep_default_na=False, low_memory=False)
    n_raw = len(frame)
    died_or_hospice = frame["discharge_disposition_id"].isin([11, 13, 14, 19, 20, 21])
    frame = frame.loc[~died_or_hospice].reset_index(drop=True)
    y = (frame.pop("readmitted") == "<30").to_numpy(dtype=int)
    groups = frame.pop("patient_nbr").to_numpy()
    frame = frame.drop(columns=["encounter_id", "weight"])
    for column in ("diag_1", "diag_2", "diag_3"):
        frame[column] = frame[column].map(icd9_group)
    frame["age"] = frame["age"].str.extract(r"\[(\d+)-").astype(float)[0] + 5  # "[70-80)" -> 75
    for column in ("admission_type_id", "discharge_disposition_id", "admission_source_id"):
        frame[column] = frame[column].astype(str)
    categorical = frame.select_dtypes(exclude="number").columns
    frame[categorical] = frame[categorical].fillna("missing")
    notes = [f"{int(died_or_hospice.sum())} of {n_raw} encounters discharged to hospice or expired removed "
             "(disposition 11, 13, 14, 19, 20, 21), as in Strack et al. 2014",
             "target = readmitted '<30'; groups = patient_nbr (StratifiedGroupKFold, no patient in train and test)",
             "dropped encounter_id, patient_nbr (identifiers) and weight (97% missing)",
             "diag_1-3 mapped to Strack et al. ICD-9 groups; missing categoricals kept as a 'missing' category",
             "categories under 1% of a training fold pooled by OneHotEncoder(min_frequency=0.01)"]
    return frame, y, groups, notes


LOADERS = {"CLN-002": load_pima, "CLN-001": load_heart, "CLN-003": load_readmission}


# ----------------------------------------------------------------------------------------------- one fold
def reducer(spec: Spec, seed: int):
    if spec.reduction == "pca":
        return PCA(n_components=spec.qubits, random_state=seed)
    if spec.reduction == "select":
        return SelectKBest(f_classif, k=spec.qubits)
    return "passthrough"


def view_name(spec: Spec) -> str:
    return {"pca": f"pca{spec.qubits}", "select": f"select{spec.qubits}", "none": f"all{spec.qubits}"}[spec.reduction]


def run_fold(spec: Spec, x: pd.DataFrame, y: np.ndarray, tr: np.ndarray, te: np.ndarray, repeat: int, fold: int,
             seed: int, include_quantum: bool) -> list[dict]:
    x_tr, x_te, y_tr, y_te = x.iloc[tr], x.iloc[te], y[tr], y[te]
    prep = lambda: tabular_preprocessor(x, min_frequency=spec.min_frequency)  # noqa: E731  (fresh, unfitted)
    models = {k: v for k, v in classical_models(seed, spec.class_weight).items() if k in spec.classical}
    reduced = view_name(spec)
    base = {"repeat": repeat, "fold": fold, "n_train": len(tr), "n_test": len(te)}
    rows = []

    def record(model, features, family, score, t_fit, t_pred, n_train):
        rows.append({**base, "n_train": n_train, "model": model, "features": features, "family": family,
                     **metrics(y_te, (score >= 0.5).astype(int), score), "train_s": t_fit, "infer_s": t_pred})

    def fit_classical(name, model, steps, features, xs, ys):
        pipe = Pipeline(steps + [("model", clone(model))])
        t0 = time.perf_counter(); pipe.fit(xs, ys); t1 = time.perf_counter()
        score = pipe.predict_proba(x_te)[:, 1]; t2 = time.perf_counter()
        record(name, features, "classical", score, t1 - t0, t2 - t1, len(ys))

    # With no reduction the full feature set *is* the quantum view, so label it the same and compare like for like.
    views = [("all" if spec.reduction != "none" else reduced, lambda: [("prep", prep())])]
    if spec.reduction != "none":
        views.append((reduced, lambda: [("prep", prep()), ("reduce", reducer(spec, seed))]))
    for (name, model), (features, steps) in product(models.items(), views):
        fit_classical(name, model, steps(), features, x_tr, y_tr)

    q_x, q_y, q_view = x_tr, y_tr, reduced
    if spec.quantum_train_max and len(tr) > spec.quantum_train_max:
        q_x, _, q_y, _ = train_test_split(x_tr, y_tr, train_size=spec.quantum_train_max, stratify=y_tr,
                                          random_state=seed + 100 * repeat + fold)
        q_view = f"{reduced}_sub{spec.quantum_train_max}"
        for name, model in models.items():  # same rows and features as the quantum models
            fit_classical(name, model, [("prep", prep()), ("reduce", reducer(spec, seed))], q_view, q_x, q_y)
    if not include_quantum:
        return rows

    angles = Pipeline([("prep", prep()), ("reduce", reducer(spec, seed)),
                       ("angles", MinMaxScaler(feature_range=(0.0, np.pi)))]).fit(q_x, q_y)
    a_tr, a_te = angles.transform(q_x), np.clip(angles.transform(x_te), 0, np.pi)
    if a_tr.shape[1] != spec.qubits:
        raise ValueError(f"{spec.name}: quantum view has {a_tr.shape[1]} columns, expected {spec.qubits}")
    vqc = VariationalClassifier(spec.qubits, epochs=spec.vqc_epochs, seed=seed + 100 * repeat + fold,
                                class_weight=spec.class_weight)
    t0 = time.perf_counter(); vqc.fit(a_tr, q_y); t1 = time.perf_counter()
    score = vqc.predict_proba1(a_te); t2 = time.perf_counter()
    record("VQC_angle_SEL2", q_view, "quantum (simulated)", score, t1 - t0, t2 - t1, len(q_y))
    t0 = time.perf_counter()
    s_tr = iqp_states(a_tr, spec.qubits)
    # Platt probabilities re-learn the class prior and would undo class weighting, so a weighted QSVM is scored
    # with sigmoid(decision function): its 0.5 threshold is then the SVM's own decision boundary.
    weighted = spec.class_weight is not None
    qsvm = SVC(kernel="precomputed", probability=not weighted, random_state=seed, class_weight=spec.class_weight)
    qsvm.fit(fidelity_kernel(s_tr, s_tr), q_y)
    t1 = time.perf_counter()
    k_te = fidelity_kernel(iqp_states(a_te, spec.qubits), s_tr)
    score = expit(qsvm.decision_function(k_te)) if weighted else qsvm.predict_proba(k_te)[:, 1]
    t2 = time.perf_counter()
    record("QSVM_IQP_fidelity_kernel", q_view, "quantum kernel (simulated)", score, t1 - t0, t2 - t1, len(q_y))
    return rows


def outer_splits(spec: Spec, x: pd.DataFrame, y: np.ndarray, groups, seed: int):
    for repeat in range(spec.repeats):
        if groups is not None:
            cv = StratifiedGroupKFold(n_splits=spec.folds, shuffle=True, random_state=seed + repeat)
            splits = cv.split(x, y, groups)
        else:
            cv = StratifiedKFold(n_splits=spec.folds, shuffle=True, random_state=seed + repeat)
            splits = cv.split(x, y)
        for fold, (tr, te) in enumerate(splits):
            if groups is not None and set(groups[tr]) & set(groups[te]):
                raise AssertionError(f"{spec.name}: patient in both train and test (repeat {repeat}, fold {fold})")
            yield repeat, fold, tr, te


# ----------------------------------------------------------------------------------------------- statistics
def corrected_ttest(a: np.ndarray, b: np.ndarray, n_train: float, n_test: float) -> tuple[float, float]:
    """Nadeau & Bengio (2003) corrected resampled t-test on paired per-fold scores. Returns (t, two-sided p)."""
    d = np.asarray(a, float) - np.asarray(b, float)
    j = len(d)
    var = d.var(ddof=1)
    if j < 2 or var == 0:
        return float("nan"), float("nan")
    t = d.mean() / np.sqrt((1 / j + n_test / n_train) * var)
    return float(t), float(2 * stats.t.sf(abs(t), df=j - 1))


def comparisons(results: pd.DataFrame, metric_names=("balanced_accuracy", "roc_auc")) -> pd.DataFrame:
    """Each quantum model vs. each classical model on the same view, and vs. the best classical model overall."""
    key = ["repeat", "fold"]
    quantum = results[~results["family"].eq("classical")]
    classical = results[results["family"].eq("classical")]
    best = classical.groupby(["model", "features"])["roc_auc"].mean().idxmax()
    rows = []
    for (q_model, q_view), q in quantum.groupby(["model", "features"]):
        candidates = [(m, q_view) for m in classical.loc[classical["features"].eq(q_view), "model"].unique()]
        for c_model, c_view in dict.fromkeys(candidates + [best]):
            c = classical[classical["model"].eq(c_model) & classical["features"].eq(c_view)]
            paired = q.merge(c, on=key, suffixes=("_q", "_c"))
            for metric in metric_names:
                t, p = corrected_ttest(paired[f"{metric}_q"], paired[f"{metric}_c"],
                                       paired["n_train_c"].mean(), paired["n_test_c"].mean())
                rows.append({"quantum_model": q_model, "quantum_features": q_view, "classical_model": c_model,
                             "classical_features": c_view, "metric": metric, "n_folds": len(paired),
                             "mean_quantum": paired[f"{metric}_q"].mean(), "mean_classical": paired[f"{metric}_c"].mean(),
                             "mean_difference": (paired[f"{metric}_q"] - paired[f"{metric}_c"]).mean(),
                             "t_corrected": t, "p_two_sided": p})
    return pd.DataFrame(rows)


def summarise(results: pd.DataFrame) -> pd.DataFrame:
    keys = ["family", "model", "features"]
    cols = ["accuracy", "balanced_accuracy", "precision", "recall_sensitivity", "specificity", "f1", "roc_auc",
            "pr_auc", "brier", "train_s", "infer_s"]
    agg = results.groupby(keys)[cols].agg(["mean", "std"])
    out = pd.DataFrame(index=agg.index)
    for c in cols:
        out[c] = agg[(c, "mean")].map("{:.3f}".format) + " ± " + agg[(c, "std")].map("{:.3f}".format)
    out["n_train"] = results.groupby(keys)["n_train"].mean().round().astype(int)
    return out.reset_index().sort_values(["features", "model"])


# ----------------------------------------------------------------------------------------------- driver
def run_experiment(spec: Spec, *, seed: int = 42, jobs: int = 1, include_quantum: bool = True,
                   folds_limit: int | None = None) -> dict:
    from joblib import Parallel, delayed

    x, y, groups, notes = LOADERS[spec.dataset_id]()
    started = time.time()
    splits = list(outer_splits(spec, x, y, groups, seed))[:folds_limit]
    chunks = Parallel(n_jobs=jobs)(delayed(run_fold)(spec, x, y, tr, te, rep, fold, seed, include_quantum)
                                   for rep, fold, tr, te in splits)
    results = pd.DataFrame([row for chunk in chunks for row in chunk])
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(RESULTS_DIR / f"{spec.name}_folds.csv", index=False)
    summarise(results).to_csv(RESULTS_DIR / f"{spec.name}_summary.csv", index=False)
    if include_quantum:
        comparisons(results).to_csv(RESULTS_DIR / f"{spec.name}_tests.csv", index=False, float_format="%.4g")
    meta = {"experiment": spec.experiment, "dataset_id": spec.dataset_id, "rows": int(len(x)),
            "raw_columns": int(x.shape[1]), "positives": int(y.sum()), "negatives": int(len(y) - y.sum()),
            "patients": int(len(set(groups))) if groups is not None else None,
            "cv": f"{'StratifiedGroupKFold' if groups is not None else 'StratifiedKFold'}, {spec.folds} folds x "
                  f"{spec.repeats} repeats, seeds {seed}..{seed + spec.repeats - 1}",
            "qubits": spec.qubits, "quantum_view": view_name(spec), "quantum_train_max": spec.quantum_train_max,
            "vqc": f"angle (RY) encoding, 2 StronglyEntanglingLayers, <Z0> readout, Adam lr 0.05, batch 32, "
                   f"{spec.vqc_epochs} epochs, 0.5 threshold",
            "qsvm": "IQPEmbedding (2 repeats) exact fidelity kernel, SVC C=1; "
                    + ("class-weighted, scored as sigmoid(decision function)" if spec.class_weight
                       else "Platt probabilities"),
            "decision_threshold": 0.5, "class_weight": spec.class_weight, "data_notes": notes + spec.notes,
            "wall_clock_s": round(time.time() - started, 1), "parallel_jobs": jobs, "environment": environment()}
    (RESULTS_DIR / f"{spec.name}_run.json").write_text(json.dumps(meta, indent=2))
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiments", nargs="+", choices=sorted(SPECS))
    parser.add_argument("--jobs", type=int, default=1, help="Folds run in parallel")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--classical-only", action="store_true")
    parser.add_argument("--vqc-epochs", type=int, help="Override the VQC epochs (smoke tests)")
    parser.add_argument("--folds-limit", type=int, help="Run only the first N folds (smoke tests)")
    args = parser.parse_args(argv)
    for experiment in args.experiments:
        spec = SPECS[experiment]
        if args.vqc_epochs:
            spec.vqc_epochs = args.vqc_epochs
        meta = run_experiment(spec, seed=args.seed, jobs=args.jobs, include_quantum=not args.classical_only,
                              folds_limit=args.folds_limit)
        print(f"{experiment} done in {meta['wall_clock_s']} s")
        print(pd.read_csv(RESULTS_DIR / f"{spec.name}_summary.csv")[
            ["model", "features", "balanced_accuracy", "roc_auc", "brier", "train_s"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
