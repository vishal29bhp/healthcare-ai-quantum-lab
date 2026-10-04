# Healthcare datasets for classical, quantum and hybrid ML research

This is a catalogue of 117 healthcare datasets in six categories, with honest per-dataset verification status, an approval-gated acquisition and validation toolchain, QML feasibility estimates, and a first classical-vs-quantum (simulated) benchmark.

> **Status as of 2026-10-04.** Metadata was verified from landing pages. Downloads from source repositories have **not** run yet, because this batch's cloud environment blocked every data host (HTTP 403). One dataset was acquired from a package-bundled mirror and validated end to end. See [Executive summary](#a-executive-summary).

## A. Executive summary

| Item | Result |
|---|---|
| Repositories searched | The 13 in the brief (Kaggle, PhysioNet, UCI, NIH/NLM, TCIA, MIMIC-IV, WHO, CDC, data.gov.in, OpenML, Hugging Face, Harvard Dataverse, Zenodo) plus other primary hosts (Synapse, GDC, RCSB, AlphaFold DB, ChEMBL, UniProt, cBioPortal, BioLINCC, SEER, IHME, DHS, n2c2 and others) |
| Candidate datasets identified | 117 (20 imaging, 21 clinical/tabular, 20 biomedical, 20 time-series, 18 public health, 18 NLP) |
| Unique after deduplication | 117. No shared DOI or URL; 16 subset, derived or mirror relationships documented in `catalog/overlaps.csv` |
| Metadata verified | 117, all on 2026-10-04: 98 reached *Access verified* (one of them, CLN-009, went on through validation) and 19 stopped at *Source verified* |
| Downloaded and validated | 1: CLN-009 Breast Cancer Wisconsin (Diagnostic), from the copy bundled in scikit-learn. Downloaded, integrity-checked, parsed and preprocessing-validated |
| Restricted or not openly downloadable | 32: 17 registration, 5 credentialed, 6 controlled, 1 competition, 3 unknown terms |
| Remaining work | Approve and run the 15 queued open downloads once the environment allows the data hosts; resolve the 19 source-verified entries by hand (captcha or JavaScript pages); run experiments E2–E7 |

The infographic mentioned in the original brief was not attached, so discovery started from the repository list and the topics in the brief.

## Layout

```
healthcare-datasets/
  README.md                  this file
  requirements-qml.txt       adds PennyLane for the quantum benchmark
  catalog/
    master_catalog.csv / .xlsx        master view (columns of brief section B); the xlsx also has per-category,
                                      full-metadata, registry, restrictions, QML, manifest and overlap sheets
    master_catalog_full_metadata.csv  all 34 metadata fields plus the derived status
    category_views/*.csv              one file per category
    source_registry.csv               repositories, programmatic access, counts
    access_restrictions.csv           non-open datasets and their next steps
    acquisition_plan.csv              approval-gated download plan
    acquisition_manifest.csv          every acquisition attempt, honestly recorded
    qml_feasibility_matrix.csv        qubit, encoding and kernel-cost estimates
    overlaps.csv, known_relationships.csv
    records/*.json                    source of truth (verified metadata)
    assessments.csv                   our suitability judgements (kept separate from source claims)
    repositories.json, parse_config.json
  medical_imaging/ clinical_tabular/ biomedical/ time_series/ public_health/ healthcare_nlp/
    <subcategory>/README.md           generated list of datasets; raw/ (git-ignored) for permitted files
  scripts/hcds/              schema, records, acquire, validate, preprocess, status, qml, build_catalog, pipeline, benchmark
  scripts/authoring/         generator for assessments.csv
  documentation/             plan, guides and reports (below)
  experiments/               runners' outputs in results/
  logs/                      acquisition.log, validation_log.csv (evidence for the status ladder)
  tests/                     offline tests (run by the repo's CI)
```

The brief's `lung_ct`, `brain_mri` and similar folders are present, along with extra subcategories the verified datasets needed: `alzheimers_mri`, `histopathology`, `retinal`, `multi_modality`, `ehr`, `pathways`, `sleep`, `social_determinants`, `biomedical_ner` and `terminology`. The allowed set is `SUBCATEGORIES` in `scripts/hcds/schema.py`.

## Deliverables (brief Task 10)

| # | Deliverable | Where |
|---|---|---|
| 1 | Master catalogue, CSV and Excel | `catalog/master_catalog.csv`, `catalog/master_catalog.xlsx` |
| 2 | Repository-by-repository discovery summary | `documentation/discovery_plan.md` §4, `catalog/source_registry.csv` |
| 3 | Category-wise catalogue | `documentation/category_catalogue.md`, `catalog/category_views/` |
| 4 | Source and licence verification report | `documentation/source_license_report.md` |
| 5 | Access and acquisition guide | `documentation/access_acquisition_guide.md` |
| 6 | Acquisition manifest | `catalog/acquisition_manifest.csv`, `logs/acquisition.log` |
| 7 | Download and metadata scripts | `scripts/hcds/acquire.py`, `pipeline.py`, `build_catalog.py` |
| 8 | Validation and preprocessing scripts | `scripts/hcds/validate.py`, `preprocess.py` |
| 9 | Quality and suitability report | `documentation/quality_privacy_licensing.md`, suitability columns in the master catalogue |
| 10 | Quantum encoding feasibility matrix | `catalog/qml_feasibility_matrix.csv`, `documentation/qml_feasibility.md` |
| 11 | Classical-versus-quantum plan (and E1 results) | `documentation/experiment_plan.md`, `experiments/results/` |
| 12 | README | this file |

The discovery plan, catalogue schema and repository access strategy are in `documentation/discovery_plan.md`.

## Setup and execution

```bash
pip install -r requirements-dev.txt                    # from the repo root: pandas, scikit-learn, openpyxl, pytest
pip install -r healthcare-datasets/requirements-qml.txt   # optional: PennyLane for quantum models
cd healthcare-datasets/scripts

python -m hcds.build_catalog --check   # validate every metadata record
python -m hcds.pipeline --dry-run      # what would be downloaded; nothing is fetched or written
python -m hcds.pipeline                # fetch approved open rows -> validate -> rebuild the catalogue
python -m hcds.pipeline --ids CLN-001  # approve and fetch one open dataset explicitly
python -m hcds.benchmark --dataset-id CLN-009 --name CLN-009_wdbc --folds 5 --qubits 4
python -m hcds.build_catalog           # regenerate every catalogue output and report
pytest -q ../tests                     # offline tests
```

The status shown in the catalogue is derived from evidence (`scripts/hcds/status.py`). Never edit it by hand. To change what is known about a dataset, edit `catalog/records/*.json` (with a new `verified_on` date and `verification_method`) and rebuild.

## Reproducibility

- Seeds are fixed (42) for splits, models and PCA; the VQC uses `seed + fold`.
- Library versions and hardware are written to each `experiments/results/*_run.json`.
- Every acquired file has a SHA-256 in the manifest, and validation re-hashes it.
- Metadata records carry `verified_on` and `verification_method`. Repository content changes, so re-verify before publication.

## Citations

Cite each dataset as its source requests; the *Citation* column of the master catalogue copies the requested citation. The E1 benchmark uses: Wolberg, W., Mangasarian, O., Street, N., & Street, W. (1993). *Breast Cancer Wisconsin (Diagnostic)* [Dataset]. UCI. https://doi.org/10.24432/C5DW2B (CC BY 4.0), as bundled by scikit-learn. The software used is scikit-learn (Pedregosa et al., JMLR 2011) and PennyLane (Bergholm et al., arXiv:1811.04968).

## Responsible use

- This tooling never bypasses authentication, never scrapes restricted resources, and never stores credentials.
- Restricted data stays out of this repository.
- None of this is a medical device or clinical advice.
- No result here is evidence of quantum advantage.
