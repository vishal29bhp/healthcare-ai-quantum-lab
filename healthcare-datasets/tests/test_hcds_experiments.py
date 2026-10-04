"""Offline tests for the experiment runners (E2-E4, E7) and the archive checks used by validation."""
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hcds.benchmark import fidelity_kernel, iqp_states  # noqa: E402
from hcds.experiments import Spec, comparisons, corrected_ttest, icd9_group, outer_splits, run_fold  # noqa: E402
from hcds.validate import verify_sha256sums  # noqa: E402


def test_numpy_iqp_states_match_pennylane():
    pytest.importorskip("pennylane")
    from hcds.benchmark import iqp_states_pennylane

    rng = np.random.default_rng(0)
    for n_qubits in (2, 4, 6):
        x = rng.uniform(0, np.pi, size=(5, n_qubits))
        assert np.allclose(iqp_states(x, n_qubits), iqp_states_pennylane(x, n_qubits), atol=1e-12)


def test_iqp_states_are_normalised_and_kernel_is_a_fidelity():
    x = np.random.default_rng(1).uniform(0, np.pi, size=(7, 5))
    states = iqp_states(x, 5)
    assert np.allclose(np.linalg.norm(states, axis=1), 1.0)
    kernel = fidelity_kernel(states, states)
    assert np.allclose(np.diag(kernel), 1.0) and np.allclose(kernel, kernel.T)
    assert (kernel >= -1e-12).all() and (kernel <= 1 + 1e-12).all()


def test_corrected_ttest_is_more_conservative_than_naive():
    rng = np.random.default_rng(2)
    a, b = rng.normal(0.80, 0.02, 25), rng.normal(0.79, 0.02, 25)
    t, p = corrected_ttest(a, b, n_train=400, n_test=100)
    d = a - b
    naive_t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
    assert abs(t) < abs(naive_t) and 0 <= p <= 1
    assert np.isnan(corrected_ttest(a, a, 400, 100)[0])  # no variance in the differences


@pytest.mark.parametrize("code,group", [("428", "circulatory"), ("250.83", "diabetes"), ("V57", "other"),
                                        ("786", "respiratory"), ("174", "neoplasms"), (np.nan, "missing"),
                                        ("715", "musculoskeletal"), ("996", "injury"), ("599", "genitourinary")])
def test_icd9_grouping(code, group):
    assert icd9_group(code) == group


def _tabular(n=160, seed=0):
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({f"f{i}": rng.normal(size=n) for i in range(5)})
    frame["cat"] = rng.choice(["a", "b", "c"], size=n)
    frame.loc[[3, 9], "f1"] = np.nan
    y = (frame["f0"] + rng.normal(scale=0.7, size=n) > 0).astype(int).to_numpy()
    return frame, y, np.repeat(np.arange(n // 2), 2)


def test_grouped_outer_splits_keep_patients_apart():
    frame, y, groups = _tabular()
    spec = Spec("T", "X", "t", qubits=2, repeats=2, folds=4)
    splits = list(outer_splits(spec, frame, y, groups, seed=0))
    assert len(splits) == 8
    for _, _, tr, te in splits:
        assert not set(groups[tr]) & set(groups[te])


def test_run_fold_classical_views_and_subsample_rows():
    frame, y, _ = _tabular()
    spec = Spec("T", "X", "t", qubits=2, reduction="pca", classical=("LogisticRegression",), quantum_train_max=60)
    tr, te = np.arange(0, 120), np.arange(120, 160)
    rows = pd.DataFrame(run_fold(spec, frame, y, tr, te, 0, 0, seed=0, include_quantum=False))
    assert set(rows["features"]) == {"all", "pca2", "pca2_sub60"}
    assert rows.set_index("features").loc["pca2_sub60", "n_train"] == 60
    assert rows["roc_auc"].between(0, 1).all()


def test_run_fold_quantum_models_when_pennylane_installed():
    pytest.importorskip("pennylane")
    frame, y, _ = _tabular(n=80)
    spec = Spec("T", "X", "t", qubits=2, reduction="select", classical=("LogisticRegression",), vqc_epochs=1)
    rows = pd.DataFrame(run_fold(spec, frame, y, np.arange(60), np.arange(60, 80), 0, 0, seed=0, include_quantum=True))
    quantum = rows[rows["family"] != "classical"]
    assert set(quantum["model"]) == {"VQC_angle_SEL2", "QSVM_IQP_fidelity_kernel"}
    assert set(quantum["features"]) == {"select2"}
    tests = comparisons(rows.assign(repeat=0))
    assert set(tests["classical_features"]) <= {"select2", "all"}


def test_sha256sums_checks_every_member(tmp_path):
    archive = tmp_path / "db.zip"
    good, bad = b"signal", b"annotation"
    sums = f"{hashlib.sha256(good).hexdigest()} a.dat\n{hashlib.sha256(b'other').hexdigest()} b.atr\n"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("db-1.0.0/a.dat", good)
        handle.writestr("db-1.0.0/b.atr", bad)
        handle.writestr("db-1.0.0/SHA256SUMS.txt", sums)
    ok, detail = verify_sha256sums(archive)
    assert not ok and "1/2 members match (1 differ" in detail
    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as handle:
        handle.writestr("x.csv", "a,b\n1,2\n")
    assert verify_sha256sums(plain) is None
