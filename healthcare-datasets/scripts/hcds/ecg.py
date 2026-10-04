"""Experiment E7: MIT-BIH heartbeat classification (AAMI N/S/V/F), inter-patient, classical vs. simulated quantum.

    OMP_NUM_THREADS=1 python -m hcds.ecg --jobs 4   # one OpenMP thread: HistGradientBoosting stalls when oversubscribed

Split: de Chazal et al. (2004) inter-patient DS1 (train) / DS2 (test), so no patient is in both. The four paced
records (102, 104, 107, 217) are excluded as in that protocol. AAMI class Q (paced, fusion of paced, unclassifiable;
a handful of beats once paced records are gone) is kept for RR intervals but not scored, as is common practice.

Features (lead MLII, baseline removed with 200 ms then 600 ms median filters) per annotated beat:
    pre_rr, post_rr, local_rr (mean of the previous 10 RR), pre_rr / local_rr, post_rr / pre_rr,
    r_amplitude, qrs_width (contiguous span above half the R amplitude, within +-100 ms), qrs_area.
These 8 are the quantum view. The "morphology" view adds the beat waveform from -250 ms to +400 ms, decimated to
24 samples. Only the beat annotations from the reference labels are used for beat positions (no detector).

Models: on all of DS1, logistic regression and HistGradientBoosting on the 8 features, HistGradientBoosting and an
MLP on 8 features + waveform (the MLP stands in for the planned 1D-CNN; no deep-learning library is installed).
Quantum models train on class-balanced subsamples of DS1 (``--per-class`` beats per class, ``--draws`` draws), and
logistic regression, SVM-RBF and HistGradientBoosting are trained on exactly the same subsamples and features.
All scaling is fitted on training data only. Everything uses balanced class weights.
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
from scipy.ndimage import median_filter
from scipy.special import softmax
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
                             precision_recall_fscore_support, roc_auc_score)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import SVC
from sklearn.utils.class_weight import compute_sample_weight

from .benchmark import RESULTS_DIR, VariationalClassifier, environment, fidelity_kernel, iqp_states
from .experiments import raw_path

DS1 = [101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215, 220, 223, 230]
DS2 = [100, 103, 105, 111, 113, 117, 121, 123, 200, 202, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234]
AAMI = {**dict.fromkeys("NLRej", "N"), **dict.fromkeys("aAJS", "S"), **dict.fromkeys("VE", "V"), "F": "F",
        **dict.fromkeys("/fQ", "Q")}
CLASSES = ["N", "S", "V", "F"]
FEATURES = ["pre_rr", "post_rr", "local_rr", "pre_over_local_rr", "post_over_pre_rr", "r_amplitude", "qrs_width",
            "qrs_area"]
WAVE = [f"wave_{i:02d}" for i in range(24)]


def extract_record(path_stem: str) -> pd.DataFrame:
    import wfdb

    record = wfdb.rdrecord(path_stem)
    ann = wfdb.rdann(path_stem, "atr")
    fs = record.fs
    signal = record.p_signal[:, record.sig_name.index("MLII")]
    baseline = median_filter(median_filter(signal, size=int(0.2 * fs) | 1), size=int(0.6 * fs) | 1)
    x = signal - baseline
    beats = [(s, AAMI[sym]) for s, sym in zip(ann.sample, ann.symbol) if sym in AAMI]
    samples = np.array([s for s, _ in beats])
    rr = np.diff(samples) / fs
    half_win, pre_w, post_w = int(0.1 * fs), int(0.25 * fs), int(0.4 * fs)
    rows = []
    for k in range(1, len(beats) - 1):
        r, label = beats[k]
        if label == "Q" or r - pre_w < 0 or r + post_w >= len(x):
            continue
        pre, post = rr[k - 1], rr[k]
        local = rr[max(0, k - 10):k].mean()
        window = x[r - half_win:r + half_win + 1]
        amp = x[r]
        above = np.abs(window) >= 0.5 * abs(amp)
        left = right = half_win
        while left > 0 and above[left - 1]:
            left -= 1
        while right < len(window) - 1 and above[right + 1]:
            right += 1
        qrs = x[r - int(0.05 * fs):r + int(0.1 * fs) + 1]
        wave = x[r - pre_w:r + post_w][:: (pre_w + post_w) // 24][:24]
        rows.append([pre, post, local, pre / local, post / pre, amp, (right - left + 1) / fs,
                     np.abs(qrs).sum() / fs, *wave, label])
    frame = pd.DataFrame(rows, columns=FEATURES + WAVE + ["label"])
    frame.insert(0, "record", int(Path(path_stem).name))
    return frame


def build_beats(cache: Path | None = None) -> pd.DataFrame:
    if cache and cache.exists():
        return pd.read_csv(cache)
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(raw_path("TS-001")) as archive:
        archive.extractall(tmp)
        root = next(Path(tmp).glob("mit-bih-arrhythmia-database-*"))
        beats = pd.concat([extract_record(str(root / str(r))) for r in DS1 + DS2], ignore_index=True)
    if cache:
        beats.to_csv(cache, index=False)
    return beats


def multiclass_metrics(y_true, proba) -> dict:
    pred = proba.argmax(axis=1)
    labels = list(range(len(CLASSES)))
    ppv, sens, _, _ = precision_recall_fscore_support(y_true, pred, labels=labels, zero_division=0)
    out = {"accuracy": accuracy_score(y_true, pred), "balanced_accuracy": balanced_accuracy_score(y_true, pred),
           "macro_f1": f1_score(y_true, pred, average="macro", labels=labels, zero_division=0),
           "macro_roc_auc_ovr": roc_auc_score(y_true, proba, multi_class="ovr", labels=labels)}
    for i, c in enumerate(CLASSES):
        out[f"sensitivity_{c}"], out[f"ppv_{c}"] = sens[i], ppv[i]
    out["confusion_matrix"] = json.dumps(confusion_matrix(y_true, pred, labels=labels).tolist())
    return out


def balanced_draw(y: np.ndarray, per_class: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.sort(np.concatenate([rng.choice(np.flatnonzero(y == c), min(per_class, int((y == c).sum())),
                                              replace=False) for c in np.unique(y)]))


def fit_vqc_one_vs_rest(a_tr, y_tr, a_te, n_classes, epochs, seed, class_index):
    vqc = VariationalClassifier(a_tr.shape[1], epochs=epochs, seed=seed * 10 + class_index, class_weight="balanced")
    t0 = time.perf_counter(); vqc.fit(a_tr, (y_tr == class_index).astype(int)); t1 = time.perf_counter()
    scores = vqc.predict_proba1(a_te)
    return scores, t1 - t0, time.perf_counter() - t1


def run(*, per_class: int = 500, draws: int = 3, epochs: int = 30, jobs: int = 1, cache: Path | None = None) -> dict:
    from joblib import Parallel, delayed

    started = time.time()
    beats = build_beats(cache)
    beats["y"] = beats["label"].map({c: i for i, c in enumerate(CLASSES)})
    train, test = beats[beats["record"].isin(DS1)], beats[beats["record"].isin(DS2)]
    assert not set(train["record"]) & set(test["record"]), "inter-patient split violated"
    y_tr, y_te = train["y"].to_numpy(), test["y"].to_numpy()
    rows = []

    def record(model, view, n_train, draw, proba, t_fit, t_pred):
        rows.append({"model": model, "features": view, "draw": draw, "n_train": n_train, "n_test": len(y_te),
                     **multiclass_metrics(y_te, proba), "train_s": t_fit, "infer_s": t_pred})

    weights = compute_sample_weight("balanced", y_tr)
    full_models = [
        ("LogisticRegression", "eng8", FEATURES,
         Pipeline([("s", StandardScaler()), ("m", LogisticRegression(max_iter=5000, class_weight="balanced"))])),
        ("HistGradientBoosting", "eng8", FEATURES, HistGradientBoostingClassifier(class_weight="balanced", random_state=0)),
        ("HistGradientBoosting", "eng8+wave24", FEATURES + WAVE,
         HistGradientBoostingClassifier(class_weight="balanced", random_state=0)),
        ("MLP_64x32", "eng8+wave24", FEATURES + WAVE,
         Pipeline([("s", StandardScaler()), ("m", MLPClassifier((64, 32), max_iter=300, early_stopping=True,
                                                                 random_state=0))])),
    ]
    for name, view, cols, model in full_models:
        t0 = time.perf_counter()
        if name.startswith("MLP"):
            model.fit(train[cols], y_tr, m__sample_weight=weights)
        else:
            model.fit(train[cols], y_tr)
        t1 = time.perf_counter(); proba = model.predict_proba(test[cols]); t2 = time.perf_counter()
        record(name, view, len(y_tr), -1, proba, t1 - t0, t2 - t1)

    vqc_jobs = []
    prepared = []
    for draw in range(draws):
        idx = balanced_draw(y_tr, per_class, seed=draw)
        xs, ys = train[FEATURES].to_numpy()[idx], y_tr[idx]
        view = f"eng8_balanced{per_class}"
        for name, model in [("LogisticRegression", LogisticRegression(max_iter=5000, class_weight="balanced")),
                            ("SVM_RBF", SVC(probability=True, class_weight="balanced", random_state=draw)),
                            ("HistGradientBoosting", HistGradientBoostingClassifier(class_weight="balanced", random_state=draw))]:
            pipe = Pipeline([("s", StandardScaler()), ("m", model)])
            t0 = time.perf_counter(); pipe.fit(xs, ys); t1 = time.perf_counter()
            proba = pipe.predict_proba(test[FEATURES].to_numpy()); t2 = time.perf_counter()
            record(name, view, len(ys), draw, proba, t1 - t0, t2 - t1)
        angles = Pipeline([("s", StandardScaler()), ("a", MinMaxScaler(feature_range=(0.0, np.pi)))]).fit(xs)
        a_tr, a_te = angles.transform(xs), np.clip(angles.transform(test[FEATURES].to_numpy()), 0, np.pi)
        t0 = time.perf_counter()
        s_tr = iqp_states(a_tr, len(FEATURES))
        qsvm = SVC(kernel="precomputed", class_weight="balanced", decision_function_shape="ovr", random_state=draw)
        qsvm.fit(fidelity_kernel(s_tr, s_tr), ys)
        t1 = time.perf_counter()
        decision = qsvm.decision_function(fidelity_kernel(iqp_states(a_te, len(FEATURES)), s_tr))
        t2 = time.perf_counter()
        record("QSVM_IQP_fidelity_kernel", view, len(ys), draw, softmax(decision, axis=1), t1 - t0, t2 - t1)
        prepared.append((draw, view, len(ys)))
        vqc_jobs += [(draw, c, a_tr, ys, a_te) for c in range(len(CLASSES))]

    fitted = Parallel(n_jobs=jobs)(delayed(fit_vqc_one_vs_rest)(a_tr, ys, a_te, len(CLASSES), epochs, draw, c)
                                   for draw, c, a_tr, ys, a_te in vqc_jobs)
    for draw, view, n in prepared:
        mine = [out for job, out in zip(vqc_jobs, fitted) if job[0] == draw]  # ordered by class index
        ovr = np.column_stack([scores for scores, _, _ in mine])
        proba = ovr / ovr.sum(axis=1, keepdims=True)
        record("VQC_angle_SEL2_one_vs_rest", view, n, draw, proba,
               sum(t for _, t, _ in mine), sum(t for _, _, t in mine))  # summed over the 4 binary VQCs

    results = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    name = "E7_TS-001_mitbih"
    results.to_csv(RESULTS_DIR / f"{name}_runs.csv", index=False)
    metric_cols = [c for c in results.columns if c not in ("model", "features", "draw", "n_train", "n_test",
                                                           "confusion_matrix")]
    agg = results.groupby(["features", "model"])[metric_cols].agg(["mean", "std"])
    summary = pd.DataFrame(index=agg.index)
    for c in metric_cols:
        summary[c] = agg[(c, "mean")].map("{:.3f}".format) + " ± " + agg[(c, "std")].fillna(0).map("{:.3f}".format)
    summary.reset_index().to_csv(RESULTS_DIR / f"{name}_summary.csv", index=False)
    counts = {split: {c: int((frame["label"] == c).sum()) for c in CLASSES} for split, frame in
              (("DS1", train), ("DS2", test))}
    meta = {"experiment": "E7", "dataset_id": "TS-001", "split": "de Chazal 2004 inter-patient DS1 -> DS2",
            "train_records": DS1, "test_records": DS2, "beats": counts, "features": FEATURES,
            "quantum_view": "8 engineered features, standardised then rescaled to [0, pi] on the training draw",
            "subsample": f"{draws} class-balanced draws of up to {per_class} DS1 beats per class (seeds 0..{draws - 1})",
            "vqc": f"4 one-vs-rest binary VQCs (angle encoding, 2 StronglyEntanglingLayers, class-weighted BCE, "
                   f"{epochs} epochs), scores normalised to sum to 1, argmax",
            "qsvm": "IQP fidelity kernel, class-weighted multi-class SVC, softmax of one-vs-rest decision values",
            "deviation_from_plan": "1D-CNN replaced by an MLP on RR features + 24-sample waveform (no deep-learning "
                                   "library installed); class Q not scored",
            "wall_clock_s": round(time.time() - started, 1), "parallel_jobs": jobs, "environment": environment()}
    (RESULTS_DIR / f"{name}_run.json").write_text(json.dumps(meta, indent=2))
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-class", type=int, default=500)
    parser.add_argument("--draws", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--cache", type=Path, help="CSV cache for extracted beat features (keep outside git)")
    args = parser.parse_args(argv)
    meta = run(per_class=args.per_class, draws=args.draws, epochs=args.epochs, jobs=args.jobs, cache=args.cache)
    print(json.dumps({k: meta[k] for k in ("beats", "wall_clock_s")}))
    print(pd.read_csv(RESULTS_DIR / "E7_TS-001_mitbih_summary.csv")[
        ["features", "model", "balanced_accuracy", "macro_f1", "macro_roc_auc_ovr", "sensitivity_S", "ppv_S",
         "sensitivity_V", "ppv_V"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
