"""Catalogue schema, controlled vocabularies, and the verification status ladder."""
from __future__ import annotations

# Fields captured per dataset in catalog/records/*.json (one JSON array per category).
RECORD_FIELDS = [
    "dataset_id", "name", "category", "subcategory", "repository", "canonical_url", "download_or_api_url",
    "doi", "application", "modality", "file_formats", "sample_count", "subject_count", "feature_count",
    "target", "class_distribution", "geographic_coverage", "temporal_coverage", "collection_method",
    "missing_data", "annotation", "license", "access_level", "access_prerequisites", "download_method",
    "version", "citation", "checksum_or_manifest", "limitations", "mirrors", "verification_status",
    "verification_method", "verified_on", "approx_size",
]

CATEGORIES = {
    "Medical Imaging": "medical_imaging",
    "Clinical/Tabular": "clinical_tabular",
    "Biomedical/Molecular": "biomedical",
    "Physiological/Time-Series": "time_series",
    "Public Health": "public_health",
    "Medical Text and Healthcare NLP": "healthcare_nlp",
}

ID_PREFIX = {
    "IMG": "Medical Imaging",
    "CLN": "Clinical/Tabular",
    "BIO": "Biomedical/Molecular",
    "TS": "Physiological/Time-Series",
    "PH": "Public Health",
    "NLP": "Medical Text and Healthcare NLP",
}

# Subcategory folders per category (Task 6 layout plus a few the verified datasets needed).
SUBCATEGORIES = {
    "Medical Imaging": {"brain_mri", "lung_ct", "chest_xray", "alzheimers_mri", "mammography", "skin_lesions",
                        "histopathology", "retinal", "multi_modality"},
    "Clinical/Tabular": {"diabetes", "cardiovascular", "kidney", "liver", "cancer", "icu", "ehr"},
    "Biomedical/Molecular": {"genomics", "transcriptomics", "proteomics", "protein_structures", "drug_target",
                             "molecular", "pathways"},
    "Physiological/Time-Series": {"ecg", "eeg", "blood_pressure", "spo2", "icu_vitals", "wearable", "sleep"},
    "Public Health": {"epidemiology", "mortality", "vaccination", "india_health", "social_determinants"},
    "Medical Text and Healthcare NLP": {"clinical_text", "biomedical_literature", "medical_qa", "biomedical_ner",
                                        "terminology"},
}

ACCESS_LEVELS = ("open", "registration", "credentialed", "controlled", "competition", "unknown")

# Ordered status ladder (Task 4). Each stage requires every stage before it.
STATUS_LADDER = [
    "discovered",
    "source_verified",
    "access_verified",
    "downloaded",
    "integrity_verified",
    "parsed",
    "preprocessing_validated",
]
METADATA_STATUSES = STATUS_LADDER[:3]

STATUS_LABELS = {
    "discovered": "Discovered",
    "source_verified": "Source verified",
    "access_verified": "Access verified",
    "downloaded": "Downloaded",
    "integrity_verified": "Integrity verified",
    "parsed": "Parsed",
    "preprocessing_validated": "Preprocessing validated",
}

# Columns of the master catalogue (format section B of the brief), in order.
MASTER_COLUMNS = [
    "Dataset ID", "Dataset Name", "Category", "Subcategory", "Repository", "Canonical URL", "DOI", "Modality",
    "Sample Count", "Feature Count", "Target", "File Format", "License", "Access Requirements",
    "Download Method", "Dataset Version", "Classical ML Suitability", "QML Suitability", "Verification Status",
    "Limitations", "Citation",
]

MANIFEST_COLUMNS = [
    "dataset_id", "source_url", "acquisition_method", "access_prerequisites", "requested_files", "local_path",
    "download_status", "timestamp_utc", "version", "file_size_bytes", "sha256", "expected_checksum",
    "error_or_reason",
]

NOT_REPORTED = "Not reported"
NOT_VERIFIED = "Not verified"
ACCESS_RESTRICTED = "Access restricted"


def category_for_id(dataset_id: str) -> str:
    prefix = dataset_id.split("-", 1)[0]
    if prefix not in ID_PREFIX:
        raise ValueError(f"Unknown dataset id prefix: {dataset_id}")
    return ID_PREFIX[prefix]


def ladder_index(status: str) -> int:
    if status not in STATUS_LADDER:
        raise ValueError(f"Unknown status {status!r}; expected one of {STATUS_LADDER}")
    return STATUS_LADDER.index(status)
