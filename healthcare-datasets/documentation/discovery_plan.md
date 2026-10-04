# Discovery plan, catalogue schema and repository access strategy

Verification date for this batch: **2026-10-04**.

## 1. Discovery plan (as executed)

1. **Seed list.** We started from the 13 repositories in the brief plus the topics in sections B to F. The infographic the brief mentions did not come with the request, so the seed list comes from those repositories and topics. We also expanded the search to authoritative primary hosts that the brief's repositories point to: Synapse, Grand Challenge, GDC, RCSB, EBI, cBioPortal, BioLINCC, SEER, IHME, the DHS Program, n2c2 and others.
2. **Candidate selection.** For each category we picked established benchmarks plus research-grade resources that cover every subtopic in the brief. That gives 20 imaging, 21 clinical, 20 biomedical, 20 time-series, 18 public-health and 18 NLP datasets.
3. **Verification.** Six verification workers ran in parallel, one per category. Each opened the canonical landing page and, where one exists, the metadata API (UCI, OpenML, Zenodo, Dataverse, Hugging Face, Socrata and NCBI E-utilities). They recorded only values printed on those pages. When a page could not be fetched, the field says "Not verified" or "Not reported". The worker brief is reproduced in §5.
4. **Classification.** Each dataset got an access level (open, registration, credentialed, controlled, competition or unknown), the licence as stated, and a subcategory folder.
5. **Deduplication.** No two records share a DOI or canonical URL; `find_overlaps` checks this automatically. `catalog/known_relationships.csv` records subsets, derived datasets and mirrors (for example MIMIC-IV demo ⊂ MIMIC-IV, emrQA ← n2c2, HAM10000 ↔ ISIC, and MoleculeNet Tox21 vs. the Tox21 challenge). Each entry is one unique dataset and its mirrors are listed in its `mirrors` field.
6. **Acquisition.** Downloads require approval. Only `access_level == open` rows of `catalog/acquisition_plan.csv` can ever be fetched.
7. **Validation.** Each downloaded file goes through integrity checks (SHA-256 re-hash and size), parsing and profiling, then the preprocessing invariants. Each stage is logged as evidence in `logs/validation_log.csv`.

### Execution constraints in this batch

- The cloud container's egress policy returned **HTTP 403 for every data host** we probed: UCI, PhysioNet, Zenodo, OpenML, Hugging Face, Kaggle, TCIA, WHO, CDC, data.gov.in, Dataverse, NCBI, EBI, UniProt, RCSB, figshare, Mendeley and Synapse. Only PyPI and GitHub were reachable. Landing pages were read with a separate web-fetch tool that summarises pages, so the metadata is a *repository-provided claim read through that tool*. It was not parsed from raw API JSON by our scripts.
- The UCI metadata API returned the Heart Disease record (id 45) for every other id through that tool. For every UCI dataset except id 45 we discarded the API values and used the landing page instead.
- Some pages could not be read: robots.txt blocks, JavaScript-only pages or captchas (GEO, PubChem, Dataverse, Kaggle and the RCSB statistics pages). Those fields stay "Not verified" and the dataset stays at *Source verified*.

## 2. Catalogue schema

The source of truth is `catalog/records/<category>.json`, one JSON array per category. Every record has the 34 fields below. `scripts/hcds/records.py` validates them and refuses empty values, unknown access levels, ID/category mismatches, and any metadata record that claims a stage beyond *Access verified*.

| Field | Meaning |
|---|---|
| dataset_id | Stable ID: `IMG-`, `CLN-`, `BIO-`, `TS-`, `PH-` or `NLP-` plus a number |
| name, category, subcategory | Name as given by the source; one of the six categories; folder name |
| repository, canonical_url, download_or_api_url, doi | Original source and documented access points |
| application, modality, file_formats | Scientific use, data modality and formats |
| sample_count, subject_count, feature_count | Copied verbatim with units |
| target, class_distribution | Labels and their balance, if reported |
| geographic_coverage, temporal_coverage, collection_method | Cohort and provenance |
| missing_data, annotation | Data-quality notes and label provenance |
| license, access_level, access_prerequisites, download_method | Legal and technical access |
| version, citation, checksum_or_manifest, approx_size | Reproducibility information |
| limitations, mirrors | Stated limitations (our own judgements are prefixed "Assessment:"), and other hosts |
| verification_status, verification_method, verified_on | Highest metadata stage reached, how it was reached, and when |

`catalog/assessments.csv` holds **our** judgements: classical and QML suitability, encodings, sizes used for qubit estimates, and baselines. It is kept separate so that repository claims and our assessments are never mixed (constraint 12).

### Status ladder (Task 4)

`discovered → source_verified → access_verified → downloaded → integrity_verified → parsed → preprocessing_validated`

`scripts/hcds/status.py` derives each dataset's status from evidence. The first three stages come from the record. *Downloaded* requires a `success` row with a SHA-256 in `acquisition_manifest.csv`. The last three stages require `ok=true` rows in `logs/validation_log.csv`. A stage counts only if every earlier stage holds, so no status can be typed in by hand.

## 3. Repository access strategy

| Repository | Programmatic route | Access model | Strategy |
|---|---|---|---|
| Kaggle | `kaggle` CLI with your own API token | Account; uploader-set licence; competition rules | Prefer the canonical upstream source and record Kaggle copies as mirrors. Never store tokens in the repo |
| PhysioNet | `wget -r -N -c -np`, get-zip URL, `wfdb`; SHA256SUMS.txt | Open, restricted or credentialed per project | Fetch open projects automatically after approval. Credentialed projects (MIMIC-IV, eICU, MIMIC-CXR, MIMIC-IV-Note, MedNLI) are documented only |
| UCI | `static/public/<id>/<slug>.zip`, `ucimlrepo` | Open, mostly CC BY 4.0 | Automatic after approval; no upstream checksum, so we hash on arrival |
| NIH/NLM/NCBI | E-utilities, FTP, UTS API | Open (PubMed, MeSH, GEO) or licence (UMLS, SNOMED CT) | Metadata first; licensed terminologies documented only |
| TCIA | NBIA Data Retriever, `tcia_utils` | Mostly CC BY; some limited access | Large DICOM collections: document only and download on user request |
| WHO GHO | OData API | Open, WHO terms | API pulls of chosen indicators |
| CDC | Socrata SODA API, program downloads | Public domain, plus WONDER DUA | Socrata metadata and CSV after approval. WONDER needs a click-through, so it is documented only |
| data.gov.in | API with a free key | GODL-India | Registration is needed for the API key, so access steps only |
| OpenML | JSON API with an md5 checksum | Open | Automatic; the md5 is verified |
| Hugging Face | Hub API, `datasets` | Per card; some gated | Ungated and openly licensed: automatic. Gated: document only |
| Harvard Dataverse | Native API with per-file MD5 | Per dataset | Automatic if the terms allow; guestbook or terms acceptance is left to the user |
| Zenodo | Records API with per-file md5 | Per record | Automatic if open; md5 verified |

## 4. Repository-by-repository discovery summary

`catalog/source_registry.csv` holds per-repository counts. Counts use first-match attribution, so each dataset is counted once:

| Repository | Datasets catalogued | Notes |
|---|---|---|
| UCI Machine Learning Repository | 16 | Clinical, sequence and wearable sets; most are CC BY 4.0 |
| PhysioNet (non-MIMIC) | 17 | ECG, EEG, sleep, PPG, wearable and ICU challenge sets; mostly ODC-By or ODbL; SHA256SUMS published |
| MIMIC family (PhysioNet) | 6 | MIMIC-IV, demo, Note, CXR, Waveform III/IV; credentialed except the demo and waveform sets |
| NIH / NLM / NCBI | 10 | PubMed, PMC OA, MeSH, UMLS, NCBI Disease and others |
| CDC | 7 | NNDSS, PLACES, NCHS causes of death, BRFSS, NHANES, WONDER, SVI |
| Kaggle | 4 | Brain tumour MRI (Nickparvar), stroke prediction, APTOS 2019, BraTS 2021 (Kaggle task 2; Synapse hosts task 1). The stroke data's uploader cites a confidential source, which is flagged |
| TCIA | 4 | UPENN-GBM, LIDC-IDRI, NLST, CBIS-DDSM |
| WHO | 3 | GHO API, Mortality Database, WUENIC |
| data.gov.in / India | 3 | NFHS-5, HMIS, Rural Health Statistics; none states a licence on the page |
| Zenodo | 2 | MedMNIST v2 and PatchCamelyon |
| OpenML / Hugging Face / Harvard Dataverse | 1 each | Pima diabetes (OpenML 37); MedMCQA (PubMedQA and BC5CDR are listed as HF mirrors of other primaries); HAM10000 (Dataverse blocked by robots.txt, so it was verified through the Sci Data paper) |
| Other authoritative hosts | 41 | Synapse, GDC, RCSB, AlphaFold DB, ChEMBL, UniProt, cBioPortal, BioLINCC, SEER, IHME, DHS, n2c2 and others |

## 5. Verification worker brief (reproducibility)

Each worker followed the same rules:
- fetch the canonical page or metadata endpoint;
- never invent values;
- copy counts with their units;
- quote licences;
- mark its own judgements "Assessment:";
- claim at most `access_verified`;
- record the `verification_method` and `verified_on` date.

The full rules are in the `verification_method` field of each record, and the controlled vocabularies are in `scripts/hcds/schema.py`.
