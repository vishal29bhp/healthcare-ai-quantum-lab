# Dataset access and acquisition guide

The per-dataset rows are in `catalog/access_restrictions.csv` (the 32 non-open datasets) and `catalog/master_catalog.csv` (the *Access Requirements* column). This guide explains the workflow and each access tier.

## Acquisition workflow

```bash
cd healthcare-datasets/scripts
python -m hcds.pipeline --dry-run          # what the plan would do; writes nothing
# approve rows: set approved=yes in catalog/acquisition_plan.csv, or name IDs explicitly:
python -m hcds.pipeline --ids CLN-001 CLN-002 TS-001
```

`hcds.pipeline` runs `acquire` → `validate` → `preprocessing_stage` → `build_catalog`. What each stage guarantees:

- **Policy gate.** A plan row is fetched only if the dataset's catalogued `access_level` is `open` **and** the row was approved (`approved=yes`, or the ID was passed with `--ids`). Every other row gets a manifest entry with status `not_attempted` and the reason.
- **Retries and resume.** Retries use exponential backoff (2, 4, 8 and 16 s). Transfers write to a `.part` file and resume with an HTTP Range request. HTTP 401, 403, 404, 407 and 451 are *not* retried, because they signal an access or policy decision that must not be worked around.
- **Rate limiting.** By default there is at least 2 s between requests (`--min-interval`).
- **Duplicate detection.** An existing file with a matching expected SHA-256 is not fetched again. Identical content under two IDs is flagged in the manifest.
- **Integrity.** The SHA-256 and size of every file are recorded. Published checksums (the OpenML md5, Zenodo and Dataverse md5s, PhysioNet SHA256SUMS.txt) go into `expected_sha256` or `expected_md5`, and a mismatch is recorded as `checksum_mismatch`.
- **No secrets.** No credentials are read. Query strings are redacted from logs and the manifest. Raw data lands in `<category>/<subcategory>/raw/<ID>/`, which is git-ignored.

## Acquisition in this batch (honest status)

| What | Result |
|---|---|
| Direct downloads from source repositories | **Not executed.** The container's network policy returned HTTP 403 for every data host. 15 open-dataset rows are queued in `acquisition_plan.csv` with `approved=no` |
| CLN-009 Breast Cancer Wisconsin (Diagnostic) | **Downloaded, integrity checked, parsed and preprocessing-validated**, from the redistributed copy bundled in scikit-learn 1.9.1 (installed from PyPI). This is a *mirror*, not the canonical UCI zip. SHA-256 `fed3eb72…72ed`, 119,913 bytes, 569 rows × 31 columns, 0 missing cells (measured) |
| All other datasets | Metadata only; their status is at most *Access verified* |

To run the queued downloads, the project's cloud environment must allow the data hosts. Open the project's environment settings and either choose a broader network access level or add these hosts to the allowed domains: `archive.ics.uci.edu`, `physionet.org`, `openml.org`, `www.openml.org`, `zenodo.org`, `huggingface.co`, `data.cdc.gov` and `ghoapi.azureedge.net`. Then run the pipeline in a new session.

## Access tiers and next steps

| Tier | Datasets (IDs) | What you must do | What this repo stores |
|---|---|---|---|
| **Open** (85) | e.g. UCI, OpenML, open PhysioNet, TCIA open collections, CDC Socrata, WHO GHO | Approve the rows. Respect the licence (attribution for CC BY and ODC-By; ODbL share-alike for derived databases; NC licences such as Icentia11k CC BY-NC-SA and ISIC CC BY-NC exclude commercial use) | Raw files locally (git-ignored); checksums and manifest in git |
| **Registration / click-through** (17) | BraTS (Synapse), CheXpert, VinDr-Mammo (PhysioNet restricted), IDRiD, Kaggle datasets, SEER, UMLS, SNOMED CT, LOINC, BioASQ, KEGG, DrugBank, TUH EEG, CDC WONDER, DHS Program, Framingham teaching set, stroke (Kaggle) | Create an account and accept the terms yourself. Kaggle: put your API token in `~/.kaggle/kaggle.json` (never in this repo) | Metadata and access steps only, until you confirm the terms allow local storage |
| **Credentialed** (5) | MIMIC-IV, eICU-CRD, MIMIC-CXR, MIMIC-IV-Note, MedNLI | Create a PhysioNet account, complete the CITI "Data or Specimens Only Research" course, apply for credentialing, then sign each project's DUA. No sharing; no use with third-party online LLM services that violate the DUA (see the PhysioNet guidance) | Metadata only. Process data only on approved, access-controlled machines |
| **Controlled** (6) | ADNI, OASIS-3, GDC controlled tier (dbGaP), n2c2, emrQA, Framingham cohort (BioLINCC) | Submit an application or DUA and wait for approval | Metadata only |
| **Competition** (1) | APTOS 2019 | Join the competition and accept its rules on Kaggle; check whether post-competition use is allowed | Metadata only |
| **Unknown** (3) | CAMELYON16, WESAD, IHME GBD | Read the terms on the linked page before any use; IHME uses a non-commercial user agreement | Metadata only |

## Adding a dataset to the plan

1. Confirm that the record in `catalog/records/*.json` is `access_level: open` and that the licence allows local copies.
2. Add a row to `catalog/acquisition_plan.csv` with the exact file URL, a filename and any published checksum.
3. For tabular files, add the target and the `pandas.read_csv` options to `catalog/parse_config.json`.
4. Run `python -m hcds.pipeline --ids <ID>`, then commit the manifest, the logs and the rebuilt catalogue, never the raw data.
