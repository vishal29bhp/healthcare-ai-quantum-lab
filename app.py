"""Streamlit entry point for the initial Healthcare AI & Quantum Research Lab slice."""
from pathlib import Path

import pandas as pd
import streamlit as st

from healthcare_lab.data import MAX_UPLOAD_BYTES, check_dataset, fingerprint_dataset, load_dataset, profile_dataset
from healthcare_lab.experiments import run_baseline
from healthcare_lab.registry import record_experiment

st.set_page_config(page_title="Healthcare AI & Quantum Research Lab", layout="wide")
st.title("Healthcare AI & Quantum Research Lab")
st.warning("Do not upload identifiable patient data, protected health information, credentials, or secrets. Uploaded data is processed in memory only.")
st.caption(f"Accepted formats: CSV, TSV, XLSX, XLS. Maximum upload size: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

upload = st.file_uploader("Upload a tabular dataset", type=["csv", "tsv", "xlsx", "xls"])
if upload is not None:
    try:
        dataset = load_dataset(upload, upload.name)
    except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as error:
        st.error(f"Could not load dataset: {error}")
    else:
        st.subheader("Dataset preview")
        st.dataframe(dataset.head(50), use_container_width=True)
        profile = profile_dataset(dataset)
        left, middle, right = st.columns(3)
        left.metric("Rows", profile["rows"])
        middle.metric("Columns", profile["columns"])
        right.metric("Duplicate rows", profile["duplicate_rows"])
        st.subheader("Data profile")
        st.dataframe(pd.DataFrame({"data_type": profile["data_types"], "missing_values": profile["missing_values"]}))
        st.subheader("Summary statistics")
        st.dataframe(dataset.describe(include="all").T, use_container_width=True)

        st.subheader("Classical ML baseline")
        target = st.selectbox("Target column", dataset.columns)
        task = st.radio("Task", ["classification", "regression"], horizontal=True)
        issues = check_dataset(dataset, target)
        if issues:
            st.warning("Data checks flagged:\n\n" + "\n".join(f"- {issue}" for issue in issues))
        else:
            st.caption("Data checks: no constant, identifier-like, highly missing, or leaking columns found.")
        seed = st.number_input("Random seed", min_value=0, max_value=2_147_483_647, value=42, step=1)
        cv_folds = st.number_input("Cross-validation folds (0 to skip)", min_value=0, max_value=20, value=5, step=1)
        if st.button("Run baseline", type="primary"):
            try:
                result = run_baseline(dataset, target, task, int(seed), int(cv_folds))
                fingerprint = fingerprint_dataset(dataset)
                record_experiment(Path("experiments.sqlite3"), fingerprint, *dataset.shape, target, result)
            except (ValueError, TypeError) as error:
                st.error(str(error))
            else:
                st.success(f"Saved metadata-only experiment record. Dataset fingerprint: `{fingerprint[:12]}…`")
                for note in result.notes:
                    st.info(note)
                st.json({
                    "model": result.model_name,
                    "train_rows": result.train_rows,
                    "test_rows": result.test_rows,
                    "held_out_metrics": result.metrics,
                    "cv_folds": result.cv_folds,
                    "cv_metrics": result.cv_metrics,
                })

st.divider()
st.header("QML research roadmap")
st.info("Planned—not implemented: quantum feature maps, variational quantum classifiers, hybrid quantum-classical optimization, simulator and hardware benchmarking, and noise-aware evaluation.")
st.caption("Implemented today: reproducible classical tabular ML baselines only. No quantum experiment, quantum hardware execution, or quantum advantage claim is made.")
