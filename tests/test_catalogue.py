import json
import zipfile

import pytest

from healthcare_lab import catalogue as catalogue_module
from healthcare_lab.catalogue import (
    complete_lines,
    licence_family,
    load_catalogue,
    preview_kind,
    read_head,
    sniff_separator,
    table_preview_options,
    zip_members,
)

MANIFEST_HEADER = ("dataset_id,source_url,acquisition_method,access_prerequisites,requested_files,local_path,"
                   "download_status,timestamp_utc,version,file_size_bytes,sha256,expected_checksum,error_or_reason\n")


def make_root(tmp_path):
    """A two-dataset catalogue: CLN-001 with a downloaded CSV and zip, BIO-001 with nothing downloaded."""
    root = tmp_path / "healthcare-datasets"
    (root / "catalog" / "records").mkdir(parents=True)
    (root / "logs").mkdir()
    base = {"category": "Clinical/Tabular", "subcategory": "cardiovascular", "repository": "UCI",
            "canonical_url": "https://example.org/d", "modality": "Tabular", "sample_count": "3", "license": "CC BY 4.0",
            "access_level": "open", "verification_status": "access_verified", "application": "Classification",
            "verified_on": "2026-10-04", "verification_method": "test", "doi": "10.1/x"}
    records = [dict(base, dataset_id="CLN-001", name="Heart"),
               dict(base, dataset_id="BIO-001", name="Genes", category="Biomedical/Molecular",
                    subcategory="genomics", license="Not reported", access_level="registration")]
    (root / "catalog" / "records" / "all.json").write_text(json.dumps(records), encoding="utf-8")
    raw = root / "clinical_tabular" / "cardiovascular" / "raw" / "CLN-001"
    raw.mkdir(parents=True)
    (raw / "heart.csv").write_text("age;label\n50;1\n61;0\n", encoding="utf-8")
    with zipfile.ZipFile(raw / "heart.zip", "w") as archive:
        archive.writestr("data/heart.tsv", "age\tlabel\n50\t1\n")
        archive.writestr("data/signal.dat", b"\x00\x01")
    (root / "catalog" / "acquisition_manifest.csv").write_text(
        MANIFEST_HEADER
        + "CLN-001,https://x/heart.csv,https,None,heart.csv,clinical_tabular/cardiovascular/raw/CLN-001/heart.csv,"
          "success,2026-10-04T00:00:00Z,,20,abc,,\n"
        + "CLN-001,https://x/heart.zip,https,None,heart.zip,clinical_tabular/cardiovascular/raw/CLN-001/heart.zip,"
          "success,2026-10-04T00:00:00Z,,20,def,,\n"
        + "CLN-001,https://x/evil,https,None,evil,../../outside.csv,success,2026-10-04T00:00:00Z,,1,ghi,,\n",
        encoding="utf-8")
    (root / "logs" / "validation_log.csv").write_text(
        'dataset_id,stage,ok,timestamp_utc,details\nCLN-001,integrity_verified,true,2026-10-04T00:00:00Z,"{""ok"": true}"\n',
        encoding="utf-8")
    (root / "catalog" / "overlaps.csv").write_text("dataset_id_a,dataset_id_b,reason\nCLN-001,BIO-001,test link\n",
                                                   encoding="utf-8")
    (tmp_path / "outside.csv").write_text("secret\n", encoding="utf-8")
    return root


def test_licence_families_group_free_text():
    assert licence_family("CC BY 4.0 (Creative Commons Attribution 4.0 International)") == "CC BY"
    assert licence_family("Academic: CC BY-NC 4.0; Open Data subset: CC0") == "CC BY-NC (non-commercial)"
    assert licence_family("Open Data Commons Attribution License v1.0") == "ODC-By"
    assert licence_family("PhysioNet Credentialed Health Data License 1.5.0") == "PhysioNet credentialed"
    assert licence_family("n2c2 DUA") == "DUA / custom terms"
    assert licence_family("UMLS Metathesaurus License (individual, no charge)") == "DUA / custom terms"
    assert licence_family("Not reported (UCI page)") == "Not reported"


def test_rows_derive_status_and_local_files(tmp_path):
    cat = load_catalogue(make_root(tmp_path))
    rows = {row["ID"]: row for row in cat.rows()}
    assert rows["CLN-001"]["Status"] == "Integrity verified"
    assert rows["CLN-001"]["Downloaded"] is True
    assert rows["BIO-001"]["Status"] == "Access verified"
    assert rows["BIO-001"]["Access"] == "Registration"
    assert rows["BIO-001"]["Downloaded"] is False
    assert [p.name for p in cat.local_files("CLN-001")] == ["heart.csv", "heart.zip"]
    assert cat.related("BIO-001") == [{"ID": "CLN-001", "Name": "Heart", "Relationship": "test link"}]


def test_manifest_paths_cannot_escape_root(tmp_path):
    cat = load_catalogue(make_root(tmp_path))
    assert cat.resolve("../../outside.csv") is None
    assert all(p.name != "outside.csv" for p in cat.local_files("CLN-001"))


def test_previews_read_only_a_prefix(tmp_path):
    root = make_root(tmp_path)
    archive = root / "clinical_tabular" / "cardiovascular" / "raw" / "CLN-001" / "heart.zip"
    members = zip_members(archive)
    assert [(m["Member"], m["Kind"]) for m in members] == [("data/heart.tsv", "table"), ("data/signal.dat", "binary")]
    assert read_head(archive, "data/heart.tsv", limit=5) == b"age\tl"
    assert complete_lines(b"a,b\n1,2\n3,", truncated=True) == "a,b\n1,2\n"
    assert sniff_separator("age;label\n50;1\n", "heart.csv") == ";"
    assert sniff_separator("x", "data.tsv") == "\t"
    assert preview_kind("RECORDS.hea") == "text"
    assert preview_kind("scan.PNG") == "image"


def test_parse_config_applies_to_plain_csv_only(tmp_path):
    root = make_root(tmp_path)
    (root / "catalog" / "parse_config.json").write_text(
        json.dumps({"CLN-001": {"read_options": {"skiprows": 1, "header": None}}}), encoding="utf-8")
    cat = load_catalogue(root)
    assert table_preview_options(cat, "CLN-001", "heart.csv", in_zip=False) == {"skiprows": 1, "header": None}
    assert table_preview_options(cat, "CLN-001", "heart.tsv", in_zip=True) == {}


def test_real_catalogue_loads():
    cat = load_catalogue()
    assert len(cat.records) >= 100
    assert all(row["Status"] for row in cat.rows())


def run_page(monkeypatch, root=None):
    testing = pytest.importorskip("streamlit.testing.v1")
    import streamlit as st

    if root is not None:
        monkeypatch.setattr(catalogue_module, "DEFAULT_ROOT", root)
    st.cache_data.clear()
    st.cache_resource.clear()
    app = testing.AppTest.from_file("../pages/1_Dataset_Explorer.py", default_timeout=60)
    return app.run()


def test_explorer_page_renders_and_filters(monkeypatch):
    app = run_page(monkeypatch)
    assert not app.exception
    assert app.title[0].value == "Dataset Explorer"
    app.sidebar.multiselect[0].select("Medical Imaging").run()
    assert not app.exception
    assert all(value.startswith("IMG-") for value in app.selectbox[0].options)


def test_explorer_page_previews_local_files(monkeypatch, tmp_path):
    app = run_page(monkeypatch, make_root(tmp_path))
    assert not app.exception
    assert app.selectbox[0].value == "CLN-001"
    assert "CLN-001 · Heart" in [header.value for header in app.header]
    assert len(app.dataframe) >= 3
    app.selectbox(key="file-CLN-001").select_index(1).run()
    assert not app.exception
