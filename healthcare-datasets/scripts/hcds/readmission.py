"""E4: 30-day readmission on Diabetes 130-US hospitals (CLN-003), classical vs. simulated quantum.

    python -m hcds.readmission --subsample 3000 --qubits 8 --vqc-epochs 15

Two views, both split with StratifiedGroupKFold on ``patient_nbr`` so no patient is in train and test:

- full cohort: LR and HistGB on all encounters and all features (one-hot categoricals with levels under 100
  encounters pooled as "infrequent", in-fold imputation);
- subsample: one random encounter per patient for a stratified sample of patients, then LR, HistGB, VQC and
  QSVM on the same PCA-reduced features (imputation, encoding, scaling and PCA fitted on training folds only).

Encounters ending in death or hospice (discharge_disposition_id 11, 13, 14, 19, 20, 21) are excluded, since those
patients cannot be readmitted. The positive class is ``readmitted == "<30"``.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, StandardScaler
from sklearn.svm import SVC

from . import ROOT
from .benchmark import (RESULTS_DIR, VariationalClassifier, compare, environment, fidelity_kernel, iqp_states,
                        metrics, summarise)
from .status import read_csv_rows
from .validate import PARSE_CONFIG, file_config, read_tabular

EXCLUDED_DISPOSITIONS = {11, 13, 14, 19, 20, 21}  # expired or hospice (IDS_mapping.csv)
ID_COLUMNS = ["admission_type_id", "discharge_disposition_id", "admission_source_id"]  # codes, not quantities


def load_cohort() -> tuple[pd.DataFrame, pd.Series, pd.Series, dict]:
    from .acquire import MANIFEST_PATH

    config = json.loads(PARSE_CONFIG.read_text())
    rows = [r for r in read_csv_rows(MANIFEST_PATH) if r["dataset_id"] == "CLN-003" and r["download_status"] == "success"]
    if not rows:
        raise SystemExit("CLN-003 has no successful acquisition in the manifest; run hcds.pipeline first")
    path = ROOT / rows[-1]["local_path"]
    cfg = file_config(config, "CLN-003", path.name)
    frame = read_tabular(path, **cfg["read_options"])
    before = len(frame)
    frame = frame[~frame["discharge_disposition_id"].isin(EXCLUDED_DISPOSITIONS)].reset_index(drop=True)
    y = (frame.pop("readmitted") == "<30").astype(int)
    groups = frame.pop("patient_nbr")
    frame = frame.drop(columns=["encounter_id"])
    frame[ID_COLUMNS] = frame[ID_COLUMNS].astype(str)
    info = {"rows_raw": before, "rows_after_exclusion": len(frame), "excluded_death_or_hospice": before - len(frame),
            "patients": int(groups.nunique()), "positives": int(y.sum())}
    return frame, y, groups, info


def preprocessor(features: pd.DataFrame) -> ColumnTransformer:
    numeric = features.select_dtypes(include="number").columns.tolist()
    categorical = [c for c in features.columns if c not in numeric]
    return ColumnTransformer([
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
        ("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=100, sparse_output=False)),
        ]), categorical),
    ])


def classical_models(seed: int) -> dict:
    return {"LogisticRegression": LogisticRegression(max_iter=3000, random_state=seed),
            "HistGradientBoosting": HistGradientBoostingClassifier(random_state=seed)}


def fit_score(pipe, x_tr, y_tr, x_te):
    t0 = time.perf_counter(); pipe.fit(x_tr, y_tr); t1 = time.perf_counter()
    score = pipe.predict_proba(x_te)[:, 1]; t2 = time.perf_counter()
    return score, t1 - t0, t2 - t1


def run_full(x: pd.DataFrame, y: pd.Series, groups: pd.Series, folds: int, seed: int) -> pd.DataFrame:
    rows = []
    cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    for fold, (tr, te) in enumerate(cv.split(x, y, groups)):
        assert not set(groups.iloc[tr]) & set(groups.iloc[te]), "patient leakage across folds"
        for name, model in classical_models(seed).items():
            pipe = Pipeline([("prep", preprocessor(x)), ("model", clone(model))])
            score, tt, ti = fit_score(pipe, x.iloc[tr], y.iloc[tr], x.iloc[te])
            rows.append({"repeat": 0, "fold": fold, "model": name, "features": "all", "family": "classical",
                         **metrics(y.iloc[te], (score >= 0.5).astype(int), score), "train_s": tt, "infer_s": ti})
    return pd.DataFrame(rows)


def patient_subsample(x, y, groups, n: int, seed: int):
    """One random encounter per patient, then a stratified sample of n patients."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(x))
    first = pd.Series(order).groupby(groups.iloc[order].to_numpy()).first().to_numpy()
    pos, neg = first[y.iloc[first].to_numpy() == 1], first[y.iloc[first].to_numpy() == 0]
    n_pos = int(round(n * len(pos) / len(first)))
    chosen = np.concatenate([rng.choice(pos, n_pos, replace=False), rng.choice(neg, n - n_pos, replace=False)])
    return x.iloc[chosen].reset_index(drop=True), y.iloc[chosen].reset_index(drop=True), groups.iloc[chosen].reset_index(drop=True)


def run_subsample(x, y, groups, *, n_qubits: int, folds: int, seed: int, vqc_epochs: int) -> pd.DataFrame:
    rows = []
    cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    for fold, (tr, te) in enumerate(cv.split(x, y, groups)):
        assert not set(groups.iloc[tr]) & set(groups.iloc[te]), "patient leakage across folds"
        x_tr, x_te, y_tr, y_te = x.iloc[tr], x.iloc[te], y.iloc[tr].to_numpy(), y.iloc[te].to_numpy()
        for name, model in classical_models(seed).items():
            for features in ("all", f"pca{n_qubits}"):
                steps = [("prep", preprocessor(x))]
                if features != "all":
                    steps.append(("pca", PCA(n_components=n_qubits, random_state=seed)))
                score, tt, ti = fit_score(Pipeline(steps + [("model", clone(model))]), x_tr, y_tr, x_te)
                rows.append({"repeat": 0, "fold": fold, "model": name, "features": features, "family": "classical",
                             **metrics(y_te, (score >= 0.5).astype(int), score), "train_s": tt, "infer_s": ti})
        angles = Pipeline([("prep", preprocessor(x)), ("pca", PCA(n_components=n_qubits, random_state=seed)),
                           ("angles", MinMaxScaler(feature_range=(0.0, np.pi)))]).fit(x_tr)
        q_tr, q_te = angles.transform(x_tr), np.clip(angles.transform(x_te), 0, np.pi)
        vqc = VariationalClassifier(n_qubits, epochs=vqc_epochs, seed=seed + fold)
        t0 = time.perf_counter(); vqc.fit(q_tr, y_tr); t1 = time.perf_counter()
        score = vqc.predict_proba1(q_te); t2 = time.perf_counter()
        rows.append({"repeat": 0, "fold": fold, "model": "VQC_angle_SEL2", "features": f"pca{n_qubits}",
                     "family": "quantum (simulated)", **metrics(y_te, (score >= 0.5).astype(int), score),
                     "train_s": t1 - t0, "infer_s": t2 - t1})
        t0 = time.perf_counter()
        s_tr, s_te = iqp_states(q_tr, n_qubits), iqp_states(q_te, n_qubits)
        qsvm = SVC(kernel="precomputed", probability=True, random_state=seed).fit(fidelity_kernel(s_tr, s_tr), y_tr)
        t1 = time.perf_counter()
        score = qsvm.predict_proba(fidelity_kernel(s_te, s_tr))[:, 1]; t2 = time.perf_counter()
        rows.append({"repeat": 0, "fold": fold, "model": "QSVM_IQP_fidelity_kernel", "features": f"pca{n_qubits}",
                     "family": "quantum kernel (simulated)", **metrics(y_te, (score >= 0.5).astype(int), score),
                     "train_s": t1 - t0, "infer_s": t2 - t1})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subsample", type=int, default=3000)
    parser.add_argument("--skip-full", action="store_true", help="Only run the subsample comparison")
    parser.add_argument("--qubits", type=int, default=8)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--vqc-epochs", type=int, default=15)
    parser.add_argument("--name", default="E4_CLN-003_readmission")
    args = parser.parse_args(argv)
    started = time.time()
    x, y, groups, info = load_cohort()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not args.skip_full:
        full = run_full(x, y, groups, args.folds, args.seed)
        full.to_csv(RESULTS_DIR / f"{args.name}_full_folds.csv", index=False)
        summarise(full).to_csv(RESULTS_DIR / f"{args.name}_full_summary.csv", index=False)
        print(summarise(full).to_string(index=False))
    xs, ys, gs = patient_subsample(x, y, groups, args.subsample, args.seed)
    sub = run_subsample(xs, ys, gs, n_qubits=args.qubits, folds=args.folds, seed=args.seed, vqc_epochs=args.vqc_epochs)
    sub.to_csv(RESULTS_DIR / f"{args.name}_subsample_folds.csv", index=False)
    summary = summarise(sub)
    summary.to_csv(RESULTS_DIR / f"{args.name}_subsample_summary.csv", index=False)
    compare(sub, len(xs), args.folds, ("LogisticRegression", f"pca{args.qubits}")).to_csv(
        RESULTS_DIR / f"{args.name}_subsample_comparisons.csv", index=False)
    meta = {"dataset": args.name, **info, "subsample_rows": len(xs), "subsample_positives": int(ys.sum()),
            "subsample_patients": int(gs.nunique()), "folds": args.folds, "split": "StratifiedGroupKFold on patient_nbr",
            "seed": args.seed, "qubits": args.qubits, "vqc_epochs": args.vqc_epochs,
            "wall_clock_s": round(time.time() - started, 1), "environment": environment()}
    (RESULTS_DIR / f"{args.name}_run.json").write_text(json.dumps(meta, indent=2))
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
