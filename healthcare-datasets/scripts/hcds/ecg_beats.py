"""E7: MIT-BIH Arrhythmia (TS-001) beat classification, inter-patient DS1 -> DS2, classical vs. simulated quantum.

    python -m hcds.ecg_beats --train-per-class 500 --qubits 8 --vqc-epochs 30 --seeds 3

Split follows de Chazal et al. (2004): models are trained on the 22 DS1 records and tested on the 22 DS2 records,
so no patient contributes beats to both sides. The four paced records (102, 104, 107, 217) are excluded, and
beat labels are mapped to the AAMI EC57 classes N, S, V, F (class Q is dropped, as is usual).

- Multi-class (N/S/V/F): HistGB on RR + morphology features, and an MLP on the raw beat window (the plan named
  a 1D-CNN; no deep-learning framework is installed here, so a scikit-learn MLP stands in and is labelled so).
- Binary AAMI tasks, VEB (V vs. rest) and SVEB (S vs. rest): VQC and IQP-kernel QSVM on 8 engineered features,
  against LR, SVM-RBF and HistGB on the same 8 features and the same class-balanced DS1 subsample, repeated over
  several subsample seeds. All scaling is fitted on DS1 training data only; every DS2 beat is scored.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import medfilt
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, balanced_accuracy_score, confusion_matrix, precision_score,
                             recall_score, roc_auc_score)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import SVC

from . import ROOT
from .benchmark import RESULTS_DIR, VariationalClassifier, environment, fidelity_kernel, iqp_states
from .status import read_csv_rows

DS1 = [101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215, 220, 223, 230]
DS2 = [100, 103, 105, 111, 113, 117, 121, 123, 200, 202, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234]
AAMI = {**dict.fromkeys("NLRej", "N"), **dict.fromkeys("AaJS", "S"), **dict.fromkeys("VE", "V"), "F": "F"}
CLASSES = ["N", "S", "V", "F"]
ENGINEERED = ["pre_rr", "post_rr", "local_rr", "pre_over_local", "r_amplitude", "qrs_width", "qrs_energy", "t_peak"]


def mitdb_zip() -> Path:
    from .acquire import MANIFEST_PATH

    rows = [r for r in read_csv_rows(MANIFEST_PATH) if r["dataset_id"] == "TS-001" and r["download_status"] == "success"]
    if not rows:
        raise SystemExit("TS-001 has no successful acquisition in the manifest; run hcds.pipeline first")
    return ROOT / rows[-1]["local_path"]


def beat_features(record_dir: Path, record: int) -> pd.DataFrame:
    import wfdb

    rec = wfdb.rdrecord(str(record_dir / str(record)))
    ann = wfdb.rdann(str(record_dir / str(record)), "atr")
    fs = rec.fs
    lead = rec.sig_name.index("MLII") if "MLII" in rec.sig_name else 0
    raw = rec.p_signal[:, lead]
    # Baseline removal with 200 ms and 600 ms median filters (de Chazal et al.).
    baseline = medfilt(medfilt(raw, int(0.2 * fs) | 1), int(0.6 * fs) | 1)
    sig = raw - baseline
    beats = [(s, AAMI[sym]) for s, sym in zip(ann.sample, ann.symbol) if sym in AAMI]
    all_r = np.array([s for s, sym in zip(ann.sample, ann.symbol) if sym in AAMI or sym in "/fQ"])
    rr = np.diff(all_r) / fs
    mean_rr = float(np.mean(rr))
    pre_w, post_w = int(0.25 * fs), int(0.4 * fs)
    window_idx = np.linspace(-pre_w, post_w, 24).astype(int)
    rows = []
    for sample, label in beats:
        i = np.searchsorted(all_r, sample)
        if i < 1 or i >= len(all_r) - 1 or sample - pre_w < 0 or sample + post_w >= len(sig):
            continue  # first/last beat lacks an RR interval or a full window
        pre_rr, post_rr = rr[i - 1], rr[i]
        local_rr = float(np.mean(rr[max(0, i - 10):i]))
        qrs = sig[sample - int(0.05 * fs): sample + int(0.05 * fs)]
        r_amp = sig[sample]
        around = np.abs(sig[sample - int(0.1 * fs): sample + int(0.1 * fs)])
        width = np.count_nonzero(around >= 0.5 * np.max(around)) / fs
        t_seg = sig[sample + int(0.15 * fs): sample + int(0.4 * fs)]
        row = {"record": record, "label": label, "pre_rr": pre_rr, "post_rr": post_rr, "local_rr": local_rr,
               "pre_over_local": pre_rr / local_rr, "post_over_pre": post_rr / pre_rr, "rr_over_record_mean": pre_rr / mean_rr,
               "r_amplitude": r_amp, "qrs_width": width, "qrs_energy": float(np.sum(qrs ** 2)),
               "qrs_min": float(np.min(qrs)), "t_peak": float(t_seg[np.argmax(np.abs(t_seg))])}
        row.update({f"w{j:02d}": sig[sample + k] for j, k in enumerate(window_idx)})
        rows.append(row)
    return pd.DataFrame(rows)


def load_beats() -> pd.DataFrame:
    with zipfile.ZipFile(mitdb_zip()) as archive, tempfile.TemporaryDirectory() as tmp:
        wanted = {str(r) for r in DS1 + DS2}
        members = [m for m in archive.namelist()
                   if m.rsplit("/", 1)[-1].split(".")[0] in wanted and m.rsplit(".", 1)[-1] in ("hea", "dat", "atr")]
        archive.extractall(tmp, members=members)
        record_dir = Path(tmp) / Path(members[0]).parent
        frames = [beat_features(record_dir, r) for r in DS1 + DS2]
    beats = pd.concat(frames, ignore_index=True)
    beats["set"] = np.where(beats.record.isin(DS1), "DS1", "DS2")
    return beats


def binary_metrics(y, pred, score) -> dict:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {"sensitivity": recall_score(y, pred, zero_division=0), "ppv": precision_score(y, pred, zero_division=0),
            "specificity": tn / (tn + fp), "balanced_accuracy": balanced_accuracy_score(y, pred),
            "roc_auc": roc_auc_score(y, score), "pr_auc": average_precision_score(y, score),
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}


def multiclass(beats: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, dict]:
    train, test = beats[beats.set == "DS1"], beats[beats.set == "DS2"]
    feature_sets = {
        "HistGB_rr_morphology": ([c for c in beats.columns if c not in ("record", "label", "set") and not c.startswith("w")],
                                 HistGradientBoostingClassifier(class_weight="balanced", random_state=seed)),
        "MLP_beat_window_(CNN_substitute)": ([c for c in beats.columns if c.startswith("w")] + ["pre_rr", "post_rr", "local_rr"],
                                             MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=300, early_stopping=True,
                                                           random_state=seed)),
    }
    rows, matrices = [], {}
    for name, (cols, model) in feature_sets.items():
        pipe = Pipeline([("scale", StandardScaler()), ("model", model)])
        t0 = time.perf_counter(); pipe.fit(train[cols], train.label); t1 = time.perf_counter()
        pred = pipe.predict(test[cols])
        cm = confusion_matrix(test.label, pred, labels=CLASSES)
        matrices[name] = cm.tolist()
        for k, cls in enumerate(CLASSES):
            tp = cm[k, k]
            rows.append({"model": name, "class": cls, "support": int(cm[k].sum()),
                         "sensitivity": tp / cm[k].sum() if cm[k].sum() else float("nan"),
                         "ppv": tp / cm[:, k].sum() if cm[:, k].sum() else float("nan"), "train_s": round(t1 - t0, 2)})
        rows.append({"model": name, "class": "macro", "support": int(cm.sum()),
                     "sensitivity": balanced_accuracy_score(test.label, pred), "ppv": float("nan"),
                     "train_s": round(t1 - t0, 2)})
    return pd.DataFrame(rows), matrices


def binary_task(beats: pd.DataFrame, positive: str, *, per_class: int, n_qubits: int, vqc_epochs: int,
                seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    train, test = beats[beats.set == "DS1"], beats[beats.set == "DS2"]
    pos_idx, neg_idx = np.flatnonzero(train.label == positive), np.flatnonzero(train.label != positive)
    chosen = np.concatenate([rng.choice(pos_idx, min(per_class, len(pos_idx)), replace=False),
                             rng.choice(neg_idx, per_class, replace=False)])
    sub = train.iloc[chosen]
    cols = ENGINEERED[:n_qubits]
    x_tr, y_tr = sub[cols].to_numpy(float), (sub.label == positive).to_numpy(int)
    x_te, y_te = test[cols].to_numpy(float), (test.label == positive).to_numpy(int)
    rows = []

    def record(model, view, score, t_train, t_infer):
        rows.append({"task": f"{positive}_vs_rest", "seed": seed, "model": model, "training_data": view,
                     "features": f"engineered{len(cols)}", **binary_metrics(y_te, (score >= 0.5).astype(int), score),
                     "train_s": round(t_train, 2), "infer_s": round(t_infer, 2)})

    classical = {"LogisticRegression": LogisticRegression(max_iter=3000, random_state=seed),
                 "SVM_RBF": SVC(probability=True, random_state=seed),
                 "HistGradientBoosting": HistGradientBoostingClassifier(random_state=seed)}
    for name, model in classical.items():
        pipe = Pipeline([("scale", StandardScaler()), ("model", model)])
        t0 = time.perf_counter(); pipe.fit(x_tr, y_tr); t1 = time.perf_counter()
        score = pipe.predict_proba(x_te)[:, 1]; t2 = time.perf_counter()
        record(name, f"DS1 balanced subsample ({len(y_tr)})", score, t1 - t0, t2 - t1)
    if seed == 0:  # reference: the same features with all DS1 beats (deterministic, so run once)
        y_full = (train.label == positive).to_numpy(int)
        pipe = Pipeline([("scale", StandardScaler()),
                         ("model", HistGradientBoostingClassifier(class_weight="balanced", random_state=0))])
        t0 = time.perf_counter(); pipe.fit(train[cols].to_numpy(float), y_full); t1 = time.perf_counter()
        score = pipe.predict_proba(x_te)[:, 1]; t2 = time.perf_counter()
        record("HistGradientBoosting_balanced", f"all DS1 ({len(y_full)})", score, t1 - t0, t2 - t1)
    angles = Pipeline([("scale", StandardScaler()), ("angles", MinMaxScaler(feature_range=(0.0, np.pi)))]).fit(x_tr)
    q_tr, q_te = angles.transform(x_tr), np.clip(angles.transform(x_te), 0, np.pi)
    vqc = VariationalClassifier(n_qubits, epochs=vqc_epochs, seed=seed)
    t0 = time.perf_counter(); vqc.fit(q_tr, y_tr); t1 = time.perf_counter()
    score = vqc.predict_proba1(q_te); t2 = time.perf_counter()
    record("VQC_angle_SEL2 (simulated)", f"DS1 balanced subsample ({len(y_tr)})", score, t1 - t0, t2 - t1)
    t0 = time.perf_counter()
    s_tr = iqp_states(q_tr, n_qubits)
    qsvm = SVC(kernel="precomputed", probability=True, random_state=seed).fit(fidelity_kernel(s_tr, s_tr), y_tr)
    t1 = time.perf_counter()
    score = np.concatenate([qsvm.predict_proba(fidelity_kernel(iqp_states(chunk, n_qubits), s_tr))[:, 1]
                            for chunk in np.array_split(q_te, max(1, len(q_te) // 5000))])
    t2 = time.perf_counter()
    record("QSVM_IQP_fidelity_kernel (simulated)", f"DS1 balanced subsample ({len(y_tr)})", score, t1 - t0, t2 - t1)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train-per-class", type=int, default=500)
    parser.add_argument("--qubits", type=int, default=8)
    parser.add_argument("--vqc-epochs", type=int, default=30)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--name", default="E7_TS-001_mitdb")
    args = parser.parse_args(argv)
    started = time.time()
    beats = load_beats()
    counts = beats.groupby(["set", "label"]).size().unstack(fill_value=0)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    multi, matrices = multiclass(beats, seed=0)
    multi.to_csv(RESULTS_DIR / f"{args.name}_multiclass.csv", index=False)
    rows = []
    for positive in ("V", "S"):
        for seed in range(args.seeds):
            rows += binary_task(beats, positive, per_class=args.train_per_class, n_qubits=args.qubits,
                                vqc_epochs=args.vqc_epochs, seed=seed)
            print(f"done {positive} seed {seed}", flush=True)
    binary = pd.DataFrame(rows)
    binary.to_csv(RESULTS_DIR / f"{args.name}_binary_runs.csv", index=False)
    cols = ["sensitivity", "ppv", "specificity", "balanced_accuracy", "roc_auc", "pr_auc", "train_s", "infer_s"]
    agg = binary.groupby(["task", "model", "training_data"])[cols].agg(["mean", "std"])
    summary = pd.DataFrame(index=agg.index)
    for c in cols:
        summary[c] = agg[(c, "mean")].map("{:.3f}".format) + " ± " + agg[(c, "std")].fillna(0).map("{:.3f}".format)
    summary.reset_index().to_csv(RESULTS_DIR / f"{args.name}_binary_summary.csv", index=False)
    meta = {"dataset": args.name, "split": "inter-patient DS1 (train) / DS2 (test), de Chazal et al. 2004",
            "beats": {s: {c: int(v) for c, v in row.items()} for s, row in counts.iterrows()},
            "engineered_features": ENGINEERED[:args.qubits], "train_per_class": args.train_per_class,
            "subsample_seeds": args.seeds, "qubits": args.qubits, "vqc_epochs": args.vqc_epochs,
            "multiclass_confusion_matrices_rows_true_cols_pred": {"labels": CLASSES, **matrices},
            "wall_clock_s": round(time.time() - started, 1), "environment": environment()}
    (RESULTS_DIR / f"{args.name}_run.json").write_text(json.dumps(meta, indent=2))
    print(multi.to_string(index=False))
    print(summary.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
