# Data-quality, privacy and licensing assessment (Tasks 2, 10 and section E)

**How to read this report.** Statements tagged *[source]* are repository claims recorded on 2026-10-04. Statements tagged *[measured]* come from our own scripts. Statements tagged *[assessment]* are our judgement.

## 1. Verification coverage

| | Count |
|---|---|
| Datasets catalogued (all unique; 16 documented subset, derived or mirror relationships) | 117 |
| Access verified (landing page plus access mechanism and terms recorded) | 97 |
| Source verified only (page reached, but terms or download route not confirmed) | 19 |
| Downloaded → integrity → parsed → preprocessing validated | 1 (CLN-009, from the scikit-learn mirror) |
| Licence stated as "Not reported" or "Not verified" on the fetched page | See `documentation/source_license_report.md` |

The 19 source-verified datasets are BIO-004, BIO-012, BIO-015, CLN-004, CLN-015, CLN-017, CLN-018, CLN-019, NLP-012, NLP-017, IMG-007, IMG-014, IMG-017, IMG-019, PH-010, PH-011, PH-012, PH-016 and TS-012. Each one's `verification_method` says why it stopped there: robots.txt, JavaScript-only pages, captchas, or no licence on the page.

## 2. Data-quality concerns worth knowing before use

| Dataset | Concern |
|---|---|
| CLN-001 Heart Disease | *[source]* Missing values are coded NaN, and the target `num` (0–4) is usually binarised. *[assessment]* 303 rows give wide confidence intervals |
| CLN-002 Pima | *[source]* OpenML reports 0 missing values. *[assessment]* Physiologically impossible zeros probably encode missingness |
| CLN-003 Diabetes 130-US | *[assessment]* Repeat encounters per patient, so split on the patient identifier. High-cardinality ICD codes |
| CLN-010 Heart Failure | *[assessment]* The follow-up `time` variable leaks the outcome, so exclude it for prediction |
| CLN-011 Cervical cancer | *[source]* Patients declined some questions, so values are missing. *[assessment]* Rare positives |
| CLN-019 Stroke (Kaggle) | *[source]* The uploader cites a "confidential source" and states educational use only. *[assessment]* Provenance cannot be verified, so keep it out of any clinical claim |
| IMG-006 Kermany chest X-ray | *[source]* Counts and CC BY 4.0 come from the Kaggle mirror; the Mendeley page fetched did not state them. *[assessment]* Paediatric single-centre data; known shortcut-learning risk |
| IMG-007 NIH ChestX-ray14 | *[source]* Labels are text-mined from reports. The commonly quoted 112,120 / 30,805 / 14-label figures were **not** found on a fetched page |
| IMG-001 BraTS 2021 | *[source]* The CBICA page (2,000 cases) and the paper (2,040 patients) disagree |
| NLP-006 MedMCQA | *[source]* Hugging Face and GitHub swap the validation and test sizes, and their licences differ (Apache-2.0 vs MIT) |
| PH-007 NNDSS | *[source]* Two reads of the metadata gave different non-null totals; the count is unconfirmed |
| PH-014 OWID COVID-19 | *[source]* Archived; last updated 19 Aug 2024 |
| NLP-018 CORD-19 | *[source]* Final release 2022-06-02; no longer updated |
| BIO-019 DAVIS | *[source]* The label-unit wording on the TDC page (IC50 vs the original Kd) needs confirming |
| BIO-011 DrugBank | *[source]* Academic downloads were "temporarily paused" when checked |
| CLN-009 WDBC | *[measured]* 569 rows × 30 features, 0 missing cells, 0 duplicate rows, 212 malignant / 357 benign |

## 3. Bias and representativeness *[assessment]*

- Single-country cohorts dominate: US ICU data (MIMIC, eICU), US surveys (BRFSS, NHANES), and Indian, Vietnamese, German and Brazilian imaging sets. Report subgroup metrics, and do not transfer results across populations without external validation.
- Many imaging labels are weak, either NLP-extracted (ChestX-ray14, CheXpert, MIMIC-CXR) or from a single reader. Treat them as noisy.
- Small UCI tabular sets (n < 1,000) are useful for method development, but results on them are not evidence of clinical utility.

## 4. Privacy

- No identifiable patient data was collected, downloaded or committed. The only data file acquired (CLN-009) contains derived image features, not identifiers, and is git-ignored anyway.
- Credentialed and controlled datasets (MIMIC family, eICU, MedNLI, n2c2, ADNI, OASIS-3, GDC controlled tier) are de-identified under their own regimes, but their DUAs prohibit re-identification, redistribution and sharing. Keep them on access-controlled machines and never in this repository or its CI.
- Public-health aggregates apply small-cell suppression (CDC WONDER suppresses counts ≤ 9 *[source]*). Do not try to undo it.
- The tooling never reads credentials, and it redacts URL query strings from logs. `.gitignore` excludes `raw/` and `processed/`.

## 5. Licensing

- **Redistribution.** Even an "open" dataset is not automatically redistributable. CC BY and ODC-By need attribution. ODbL needs share-alike for derived databases. NC licences (Icentia11k, ISIC 2019/2020, QM9 per the Sci Data article, DrugBank academic, IHME) bar commercial use. The WHO Mortality Database also states non-commercial terms *[source]*.
- **No stated licence.** Where a page states no licence (for example NNDSS, BRFSS, NHANES, the data.gov.in resources, BindingDB, CAMELYON16, IDRiD and CheXpert on the fetched page), treat it as "terms unknown". Check before any redistribution. US federal works are generally public domain, but confirm per dataset *[assessment]*.
- **Terminologies.** UMLS, SNOMED CT and LOINC require accepting their licences and can only be used within those terms.
