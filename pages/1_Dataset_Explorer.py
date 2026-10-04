"""Browse the healthcare dataset catalogue, open a dataset's full record, and preview files downloaded locally."""
from __future__ import annotations

import io
import json

import pandas as pd
import streamlit as st

from healthcare_lab.catalogue import (
    PREVIEW_BYTES,
    complete_lines,
    load_catalogue,
    preview_kind,
    read_head,
    sniff_separator,
    status_order,
    table_preview_options,
    zip_members,
)

PREVIEW_ROWS = 200

st.set_page_config(page_title="Dataset Explorer", layout="wide")


@st.cache_data(show_spinner=False)
def catalogue_frame() -> pd.DataFrame:
    return pd.DataFrame(load_catalogue().rows())


@st.cache_resource(show_spinner=False)
def catalogue():
    return load_catalogue()


def options(frame: pd.DataFrame, column: str, order: list[str] | None = None) -> list[str]:
    present = set(frame[column].dropna())
    if order:
        return [value for value in order if value in present]
    return sorted(present)


def show_table_preview(data: bytes, name: str, read_options: dict, truncated: bool) -> None:
    text = complete_lines(data, truncated)
    if not read_options:
        read_options = {"sep": sniff_separator(text, name)}
    read_options.setdefault("sep", ",")
    try:
        frame = pd.read_csv(io.StringIO(text), nrows=PREVIEW_ROWS, low_memory=False,
                            on_bad_lines="skip", **read_options)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as error:
        st.warning(f"Could not parse as a table ({error}). Showing the first lines as text.")
        st.code("".join(text.splitlines(keepends=True)[:60]), language=None)
        return
    st.caption(f"First {len(frame)} rows, {frame.shape[1]} columns"
               + (" (file truncated for preview)" if truncated else ""))
    st.dataframe(frame)


def show_file_preview(cat, dataset_id: str, path, member: str | None = None) -> None:
    name = member or path.name
    kind = preview_kind(name)
    if kind == "binary":
        st.info("Binary format with no built-in preview (for example WFDB signal .dat files). "
                "Open it with the format's own tooling.")
        return
    if kind == "image":
        st.image(read_head(path, member, limit=20 * 1024 * 1024), caption=name)
        return
    data = read_head(path, member, limit=PREVIEW_BYTES + 1)
    truncated = len(data) > PREVIEW_BYTES
    data = data[:PREVIEW_BYTES]
    if kind == "table":
        show_table_preview(data, name, table_preview_options(cat, dataset_id, name, member is not None), truncated)
    else:
        lines = complete_lines(data, truncated).splitlines(keepends=True)
        st.code("".join(lines[:200]), language="json" if name.endswith(".json") else None)
        if len(lines) > 200:
            st.caption(f"Showing the first 200 of {len(lines)}+ lines.")


def show_files(cat, dataset_id: str) -> None:
    manifest = cat.manifest_rows(dataset_id)
    files = cat.local_files(dataset_id)
    if not manifest:
        st.info("No download is planned for this dataset yet (see catalog/acquisition_plan.csv).")
        return
    if not files:
        succeeded = [row for row in manifest if row["download_status"] == "success"]
        if succeeded:
            st.info("The manifest records a download, but the file is not on this machine (raw data is not "
                    "committed to git). Run the acquisition pipeline locally to fetch it:")
            st.code(f"cd healthcare-datasets/scripts && python -m hcds.pipeline --ids {dataset_id}", language="bash")
        else:
            st.info("Nothing has been downloaded for this dataset yet. The acquisition attempts are listed under "
                    "Evidence.")
        return
    labels = {str(path.relative_to(cat.root.resolve())): path for path in files}
    choice = st.selectbox("File", list(labels), key=f"file-{dataset_id}")
    path = labels[choice]
    st.caption(f"{path.stat().st_size:,} bytes")
    if preview_kind(path.name) == "zip":
        members = zip_members(path)
        st.dataframe(pd.DataFrame(members), hide_index=True, height=240)
        previewable = [m["Member"] for m in members if m["Kind"] != "binary"]
        if not previewable:
            st.info("No member of this archive has a built-in preview.")
            return
        member = st.selectbox("Preview a file inside the archive", previewable, key=f"member-{dataset_id}")
        show_file_preview(cat, dataset_id, path, member)
    else:
        show_file_preview(cat, dataset_id, path)


def field_table(record: dict, fields: list[tuple[str, str]]) -> None:
    rows = [{"Field": label, "Value": record.get(key) or "Not reported"} for key, label in fields]
    st.dataframe(pd.DataFrame(rows), hide_index=True)


def show_detail(cat, dataset_id: str) -> None:
    record = cat.records[dataset_id]
    st.header(f"{dataset_id} · {record['name']}")
    status = catalogue_frame().set_index("ID").loc[dataset_id]
    a, b, c, d = st.columns(4)
    a.metric("Status", status["Status"])
    b.metric("Access", status["Access"])
    c.metric("Licence family", status["Licence family"])
    d.metric("Local files", len(cat.local_files(dataset_id)))
    links = [f"[Landing page]({record['canonical_url']})"]
    if record.get("doi", "").startswith("10."):
        links.append(f"[DOI {record['doi']}](https://doi.org/{record['doi']})")
    st.markdown(" · ".join(links))
    st.write(record["application"])

    overview, access, ml, files, evidence = st.tabs(["Overview", "Access and licence", "ML and QML",
                                                     "Files and preview", "Evidence"])
    with overview:
        field_table(record, [
            ("category", "Category"), ("subcategory", "Subcategory"), ("repository", "Repository"),
            ("modality", "Modality"), ("sample_count", "Samples"), ("subject_count", "Subjects"),
            ("feature_count", "Features"), ("target", "Target"), ("class_distribution", "Class distribution"),
            ("file_formats", "File formats"), ("approx_size", "Approximate size"), ("version", "Version"),
            ("geographic_coverage", "Geographic coverage"), ("temporal_coverage", "Temporal coverage"),
            ("collection_method", "Collection method"), ("missing_data", "Missing data"),
            ("annotation", "Annotation"), ("limitations", "Limitations"), ("citation", "Citation"),
        ])
        related = cat.related(dataset_id)
        if related:
            st.subheader("Related datasets")
            st.dataframe(pd.DataFrame(related), hide_index=True)
    with access:
        field_table(record, [
            ("license", "Licence"), ("access_level", "Access level"), ("access_prerequisites", "Prerequisites"),
            ("download_method", "Download method"), ("download_or_api_url", "Download or API URL"),
            ("mirrors", "Mirrors"), ("checksum_or_manifest", "Published checksum"),
        ])
        restriction = cat.restrictions.get(dataset_id)
        if restriction:
            st.warning(f"**Not openly downloadable.** {restriction['next_step']}")
    with ml:
        assessment = cat.assessments.get(dataset_id)
        feasibility = cat.feasibility.get(dataset_id)
        if not assessment and not feasibility:
            st.info("No ML or QML assessment recorded for this dataset.")
        if assessment:
            field_table(assessment, [
                ("task", "Task"), ("classical_ml_suitability", "Classical ML suitability"),
                ("qml_suitability", "QML suitability"), ("label_structure", "Label structure"),
                ("class_imbalance", "Class imbalance"), ("reduction", "Dimensionality reduction"),
                ("target_qubits", "Target qubits"), ("recommended_encoding", "Recommended encoding"),
                ("recommended_qml_models", "Recommended QML models"), ("classical_baselines", "Classical baselines"),
                ("trainability_notes", "Trainability notes"),
            ])
        if feasibility:
            st.subheader("QML resource estimate")
            field_table(feasibility, [
                ("angle_qubits", "Angle-encoding qubits"), ("amplitude_qubits", "Amplitude-encoding qubits"),
                ("amplitude_state_prep_cnots", "Amplitude state-prep CNOTs"), ("basis_qubits", "Basis qubits"),
                ("zz_feature_map_entanglers", "ZZ feature-map entanglers"),
                ("qsvm_kernel_evals_full", "QSVM kernel evaluations (full)"),
                ("qsvm_max_train_samples", "QSVM max training samples"), ("simulator_tier", "Simulator tier"),
            ])
    with files:
        show_files(cat, dataset_id)
    with evidence:
        st.caption(f"Metadata verified on {record['verified_on']} by: {record['verification_method']}")
        manifest = cat.manifest_rows(dataset_id)
        if manifest:
            st.subheader("Acquisition manifest")
            st.dataframe(pd.DataFrame(manifest).drop(columns=["dataset_id"]),
                         hide_index=True)
        validation = cat.validation_rows(dataset_id)
        if validation:
            st.subheader("Validation log")
            for row in validation:
                icon = "✅" if row["ok"] == "true" else "❌"
                with st.expander(f"{icon} {row['stage']} · {row['timestamp_utc']}"):
                    try:
                        st.json(json.loads(row["details"]))
                    except json.JSONDecodeError:
                        st.write(row["details"])
        if not manifest and not validation:
            st.info("No download or validation evidence yet; status comes from metadata verification only.")


st.title("Dataset Explorer")
st.caption("Browse the 117-dataset healthcare catalogue in healthcare-datasets/. Metadata comes from "
           "catalog/records; status is derived from the acquisition manifest and validation log.")

cat = catalogue()
frame = catalogue_frame()

with st.sidebar:
    st.header("Filters")
    query = st.text_input("Search", placeholder="Name, ID, modality, repository…")
    categories = st.multiselect("Category", options(frame, "Category"))
    scoped = frame[frame["Category"].isin(categories)] if categories else frame
    subcategories = st.multiselect("Subcategory", options(scoped, "Subcategory"))
    access_levels = st.multiselect("Access", options(frame, "Access", ["Open", "Registration", "Credentialed",
                                                                       "Controlled", "Competition", "Unknown"]))
    licences = st.multiselect("Licence family", options(frame, "Licence family"))
    statuses = st.multiselect("Status", options(frame, "Status", status_order()))
    downloaded_only = st.toggle("Only datasets with files on this machine")

view = frame
for column, chosen in (("Category", categories), ("Subcategory", subcategories), ("Access", access_levels),
                       ("Licence family", licences), ("Status", statuses)):
    if chosen:
        view = view[view[column].isin(chosen)]
if downloaded_only:
    view = view[view["Downloaded"]]
if query:
    haystack = view[["ID", "Name", "Modality", "Repository", "Subcategory", "Licence"]].astype(str).agg(" ".join, axis=1)
    view = view[haystack.str.contains(query, case=False, regex=False)]

total, shown, open_count, downloaded = st.columns(4)
total.metric("Datasets in catalogue", len(frame))
shown.metric("Matching filters", len(view))
open_count.metric("Open access (matching)", int((view["Access"] == "Open").sum()))
downloaded.metric("Downloaded per manifest (matching)",
                  sum(any(r["download_status"] == "success" for r in cat.manifest_rows(i)) for i in view["ID"]))

if view.empty:
    st.info("No dataset matches these filters.")
    st.stop()

with st.expander("Counts by category and status"):
    counts = view.groupby(["Category", "Status"]).size().unstack(fill_value=0)
    st.bar_chart(counts)

columns = ["ID", "Name", "Category", "Subcategory", "Access", "Licence family", "Status", "Samples", "Size", "Repository"]
selection = st.dataframe(view[columns], hide_index=True, height=420,
                         on_select="rerun", selection_mode="single-row", key="catalogue-table")
st.caption("Select a row to open its record, or pick a dataset below.")

ids = view["ID"].tolist()
selected_rows = selection.selection.rows if selection else []
default = st.query_params.get("id")
if selected_rows and selected_rows[0] < len(ids):
    default = ids[selected_rows[0]]
index = ids.index(default) if default in ids else 0
names = dict(zip(view["ID"], view["Name"]))
dataset_id = st.selectbox("Dataset", ids, index=index, format_func=lambda i: f"{i} · {names[i]}")
st.query_params["id"] = dataset_id

st.divider()
show_detail(cat, dataset_id)
