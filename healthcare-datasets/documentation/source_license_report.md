# Source and licence verification report

Licence text is copied from the dataset's own landing page or metadata API. 'Not reported' means the page we fetched did not state a licence; it does **not** mean the data is unrestricted. Always re-read the licence before redistribution.

## Access levels

| Access level | Datasets |
|---|---|
| open | 85 |
| registration | 17 |
| controlled | 6 |
| credentialed | 5 |
| unknown | 3 |
| competition | 1 |

## Per-dataset licence and verification

| Dataset ID | Dataset Name | License (as stated) | Access level | Verified on | Method | Status |
|---|---|---|---|---|---|---|
| BIO-001 | Molecular Biology (Splice-junction Gene Sequences) | CC BY 4.0 | open | 2026-10-04 | WebFetch of UCI landing page (UCI API ?id= returned wrong dataset (Heart Disease) and was discarded) | Preprocessing validated |
| BIO-002 | Molecular Biology (Promoter Gene Sequences) | CC BY 4.0 | open | 2026-10-04 | WebFetch of UCI landing page (UCI API ?id= returned wrong dataset and was discarded) | Preprocessing validated |
| BIO-003 | gene expression cancer RNA-Seq | CC BY 4.0 | open | 2026-10-04 | WebFetch of UCI landing page (UCI API ?id= returned wrong dataset and was discarded) | Parsed |
| BIO-004 | NCBI Gene Expression Omnibus (GEO) | Not verified | open | 2026-10-04 | WebFetch of geo/ and geo/summary blocked by reCAPTCHA; E-utilities EInfo JSON (db=gds) fetched | Source verified |
| BIO-005 | NCI Genomic Data Commons (GDC) incl. TCGA | Not reported (GDC 'Data Access Policies' referenced but not quoted) | controlled | 2026-10-04 | Portal landing (JS, empty) + GDC API /status, /projects, /cases, /files + release notes + data access page | Access verified |
| BIO-006 | UniProtKB/Swiss-Prot | CC BY 4.0 ('applied to all copyrightable parts of our databases') | open | 2026-10-04 | uniprot.org pages JS-only; ExPASy relstat + rest.uniprot.org/help/license + REST search JSON fetched | Access verified |
| BIO-007 | RCSB Protein Data Bank (PDB) | CC0 1.0 Universal (data files and API data) | open | 2026-10-04 | WebFetch of rcsb.org, usage policy and file download services docs | Access verified |
| BIO-008 | AlphaFold Protein Structure Database | CC-BY-4.0 (academic and commercial use) | open | 2026-10-04 | WebFetch of homepage + download page | Access verified |
| BIO-009 | BindingDB | Not reported | open | 2026-10-04 | WebFetch of homepage + Download page | Access verified |
| BIO-010 | ChEMBL | CC BY-SA 3.0 Unported | open | 2026-10-04 | WebFetch of landing page + API status.json | Access verified |
| BIO-011 | DrugBank | Academic: CC BY-NC 4.0; Open Data subset: CC0; commercial use requires paid licence | registration | 2026-10-04 | WebFetch of homepage + releases/latest + stats | Access verified |
| BIO-012 | MoleculeNet (Tox21, BBBP, HIV, etc.) | Not reported for data (article: CC BY-NC 3.0 Unported) | open | 2026-10-04 | WebFetch of moleculenet.org/datasets-1, DeepChem docs, arXiv abstract, RSC article Table 1 | Source verified |
| BIO-013 | QM9 (Quantum chemistry structures and properties of 134 kilo molecules) | Nature article page states CC BY-NC-SA 4.0 for article and data (figshare metadata: not reported) | open | 2026-10-04 | WebFetch of figshare collection page + figshare API (collection + articles) + Sci Data article | Access verified |
| BIO-014 | Therapeutics Data Commons (TDC) | Not reported on overview; per-dataset (e.g., DAVIS/KIBA: CC BY 4.0) | open | 2026-10-04 | WebFetch of tdcommons.ai homepage + overview + DTI page | Access verified |
| BIO-015 | PubChem | Not reported on pages fetched | open | 2026-10-04 | WebFetch of docs/statistics, docs/about, docs/downloads (JS-only content); PUG-REST/eutils pccompound blocked by robots.txt | Source verified |
| BIO-016 | STRING protein-protein interaction networks | Creative Commons BY 4.0 ('All data and download files in STRING are freely available') | open | 2026-10-04 | WebFetch of cgi/access; cgi/download blocked by robots.txt | Access verified |
| BIO-017 | Reactome | Data: CC0; illustrations/icons: CC BY 4.0; software: Apache 2.0 | open | 2026-10-04 | WebFetch of homepage, license, download-data; statistics page and ContentService blocked/empty | Access verified |
| BIO-018 | KEGG | Copyright Kanehisa Laboratories; academic website use free; academic service providers need FTP academic subscription; non-academic use requires commercial licence (Pathway Solutions) | registration | 2026-10-04 | WebFetch of kegg.jp/kegg/legal.html + docs/statistics.html | Access verified |
| BIO-019 | Davis / KIBA drug-target affinity benchmarks (via TDC) | CC BY 4.0 (stated on TDC DTI page) | open | 2026-10-04 | WebFetch of TDC DTI page (twice) | Access verified |
| BIO-020 | Tox21 Data Challenge 2014 | Not reported | open | 2026-10-04 | WebFetch of challenge homepage + data.jsp | Access verified |
| CLN-001 | Heart Disease | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page + UCI API JSON (id=45; record name matches Heart Disease) | Preprocessing validated |
| CLN-002 | Pima Indians Diabetes (OpenML 'diabetes') | Public (OpenML licence field) | open | 2026-10-04 | WebFetch of OpenML JSON data API + data qualities API | Preprocessing validated |
| CLN-003 | Diabetes 130-US Hospitals for Years 1999-2008 | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Preprocessing validated |
| CLN-004 | CDC Diabetes Health Indicators | Not reported (UCI page: 'See linked dataset for licensing information') | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Source verified |
| CLN-005 | Early Stage Diabetes Risk Prediction | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Preprocessing validated |
| CLN-006 | Chronic Kidney Disease | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Integrity verified |
| CLN-007 | ILPD (Indian Liver Patient Dataset) | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Preprocessing validated |
| CLN-008 | Hepatitis C Virus (HCV) data | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Preprocessing validated |
| CLN-009 | Breast Cancer Wisconsin (Diagnostic) | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Preprocessing validated |
| CLN-010 | Heart Failure Clinical Records | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Preprocessing validated |
| CLN-011 | Cervical Cancer (Risk Factors) | CC BY 4.0 (Creative Commons Attribution 4.0 International) | open | 2026-10-04 | WebFetch of UCI landing page (UCI API not used: WebFetch returned id 45 for all ids) | Preprocessing validated |
| CLN-012 | MIMIC-IV v3.1 | PhysioNet Credentialed Health Data License 1.5.0 | credentialed | 2026-10-04 | WebFetch of PhysioNet project page | Access verified |
| CLN-013 | MIMIC-IV Clinical Database Demo | Open Data Commons Open Database License v1.0 (ODbL) | open | 2026-10-04 | WebFetch of PhysioNet project page | Parsed |
| CLN-014 | eICU Collaborative Research Database | PhysioNet Credentialed Health Data License 1.5.0 | credentialed | 2026-10-04 | WebFetch of PhysioNet project page | Access verified |
| CLN-015 | Synthea synthetic patient data (SyntheticMass) | Apache-2.0 (generator code, GitHub); sample data license not reported | open | 2026-10-04 | WebFetch of synthetichealth.github.io/synthea + GitHub repo; synthea.mitre.org/downloads failed (SSL/robots) | Source verified |
| CLN-016 | SEER Research Data | Not reported (data use agreement terms on registration) | registration | 2026-10-04 | WebFetch of seer.cancer.gov/data/ | Access verified |
| CLN-017 | Diabetes (Efron et al. 2004, LARS) | Not reported | open | 2026-10-04 | WebFetch of scikit-learn toy dataset docs; NCSU canonical page fetch failed (robots.txt disallowed) | Source verified |
| CLN-018 | METABRIC breast cancer (cBioPortal brca_metabric) | Not reported | open | 2026-10-04 | WebFetch of cBioPortal studies API (summary page is JS-rendered) | Source verified |
| CLN-019 | Stroke Prediction Dataset | Data files © Original Authors | registration | 2026-10-04 | WebFetch of Kaggle dataset API JSON (landing page JS-rendered) | Source verified |
| CLN-020 | Framingham Heart Study-Cohort (FHS-Cohort), BioLINCC | Not reported | controlled | 2026-10-04 | WebFetch of BioLINCC study page | Access verified |
| CLN-021 | Framingham Heart Study teaching dataset (BioLINCC) | Not reported | registration | 2026-10-04 | WebFetch of BioLINCC teaching datasets page | Access verified |
| NLP-001 | PubMed annual baseline (MEDLINE/PubMed XML) | Terms and Conditions in README.txt bundled with baseline/update files; downloading indicates acceptance | open | 2026-10-04 | WebFetch of pubmed.ncbi.nlm.nih.gov/download (old nlm.nih.gov page says no longer maintained); FTP listing fetch blocked by robots.txt | Access verified |
| NLP-002 | PMC Open Access Subset | Varies per article ('license terms vary'); license type recorded in per-article JSON metadata | open | 2026-10-04 | WebFetch of pmc.ncbi.nlm.nih.gov/tools/openftlist and /tools/pmcaws | Access verified |
| NLP-003 | MIMIC-IV-Note: Deidentified free-text clinical notes | PhysioNet Credentialed Health Data License 1.5.0 | credentialed | 2026-10-04 | WebFetch of PhysioNet landing page | Access verified |
| NLP-004 | MedQA (USMLE) | MIT License (repository) | open | 2026-10-04 | WebFetch of GitHub README | Access verified |
| NLP-005 | PubMedQA | MIT (GitHub repo and HF card) | open | 2026-10-04 | WebFetch of pubmedqa.github.io, GitHub README, HF API JSON + dataset card | Parsed |
| NLP-006 | MedMCQA | Apache-2.0 (HF card); MIT (GitHub repo) | open | 2026-10-04 | WebFetch of medmcqa.github.io, GitHub README, HF API JSON + card | Access verified |
| NLP-007 | BioASQ | Not reported | registration | 2026-10-04 | WebFetch of bioasq.org, /participate, /participate/data | Access verified |
| NLP-008 | n2c2 (formerly i2b2) NLP Research Data Sets | n2c2 Data Use Agreement | controlled | 2026-10-04 | WebFetch of n2c2.dbmi.hms.harvard.edu/data-sets and DBMI portal project page | Access verified |
| NLP-009 | UMLS Metathesaurus | UMLS Metathesaurus License (individual, no charge); some sources need additional agreements | registration | 2026-10-04 | WebFetch of UMLS home + Knowledge Sources download page | Access verified |
| NLP-010 | Medical Subject Headings (MeSH) | NLM Terms and Conditions (https://www.nlm.nih.gov/databases/download/terms_and_conditions.html) | open | 2026-10-04 | WebFetch of MeSH home + MeSH download page | Access verified |
| NLP-011 | NCBI Disease Corpus | Public domain notice | open | 2026-10-04 | WebFetch of NCBI landing page | Access verified |
| NLP-012 | BioCreative V CDR corpus (BC5CDR) | Public Domain Mark 1.0 (HF bigbio card); not stated on BioCreative page | open | 2026-10-04 | WebFetch of BioCreative track page + HF API/card; BioCreative corpus page 403; PMC paper blocked by captcha | Source verified |
| NLP-013 | MedNLI | PhysioNet Credentialed Health Data License 1.5.0 | credentialed | 2026-10-04 | WebFetch of PhysioNet landing page | Access verified |
| NLP-014 | SNOMED CT (US Edition / International) | SNOMED CT Affiliate License | registration | 2026-10-04 | WebFetch of NLM SNOMED CT pages + snomed.org/get-snomed | Access verified |
| NLP-015 | LOINC | LOINC License | registration | 2026-10-04 | WebFetch of loinc.org/downloads | Access verified |
| NLP-016 | emrQA | n2c2 DUA | controlled | 2026-10-04 | WebFetch of GitHub README | Access verified |
| NLP-017 | MTSamples transcribed medical reports | Not reported; may print, share or link for educational purposes with attribution to MTSamples.com | open | 2026-10-04 | WebFetch of mtsamples.com home | Source verified |
| NLP-018 | CORD-19 | Varies by paper (CC0, CC-BY, Gold OA, Green OA, others) | open | 2026-10-04 | WebFetch of GitHub README | Access verified |
| IMG-001 | BraTS 2021 (RSNA-ASNR-MICCAI Brain Tumor Segmentation) | Not reported for data (arXiv paper itself is CC BY 4.0) | registration | 2026-10-04 | WebFetch of UPenn CBICA BraTS 2021 page + arXiv abstract; Synapse page/wiki fetched but returned no dataset details | Access verified |
| IMG-002 | Brain Tumor MRI Dataset (Nickparvar) | CC BY 4.0 | registration | 2026-10-04 | WebFetch of Kaggle landing page (metadata only) + Kaggle API datasets/view JSON | Access verified |
| IMG-003 | UPENN-GBM | CC BY 4.0 | open | 2026-10-04 | WebFetch of TCIA collection page | Access verified |
| IMG-004 | LIDC-IDRI | CC BY 3.0 | open | 2026-10-04 | WebFetch of TCIA collection page | Access verified |
| IMG-005 | NLST (National Lung Screening Trial) imaging | CC BY 4.0 | open | 2026-10-04 | WebFetch of TCIA collection page | Access verified |
| IMG-006 | Chest X-Ray Images (Pneumonia), Kermany et al. | CC BY 4.0 (stated on Kaggle mirror; not shown on fetched Mendeley page) | open | 2026-10-04 | WebFetch of Mendeley landing page + Kaggle API JSON for mirror (counts/license from mirror) | Access verified |
| IMG-007 | NIH ChestX-ray14 | Not reported | open | 2026-10-04 | Box page fetched but no content (JS required); WebFetch of NIH IRP and NIH CC news pages + arXiv 1705.02315 abstract; nih.gov news release 404 | Source verified |
| IMG-008 | CheXpert | Not reported (AIMI page has Terms & Conditions; text not extracted) | registration | 2026-10-04 | WebFetch of Stanford ML Group page + Stanford AIMI dataset page; AIMI Azure page returned no content | Access verified |
| IMG-009 | MIMIC-CXR v2.0.0 | PhysioNet Credentialed Health Data License 1.5.0 | credentialed | 2026-10-04 | WebFetch of PhysioNet project page | Access verified |
| IMG-010 | OASIS-3 | Not reported (OASIS Data Use Agreement; acknowledgment required) | controlled | 2026-10-04 | WebFetch of OASIS-3 page | Access verified |
| IMG-011 | ADNI (Alzheimer's Disease Neuroimaging Initiative) | Not reported (ADNI Data Use Agreement and publication policies) | controlled | 2026-10-04 | WebFetch of ADNI homepage + ADNI data access page | Access verified |
| IMG-012 | CBIS-DDSM | CC BY 3.0 | open | 2026-10-04 | WebFetch of TCIA collection page | Access verified |
| IMG-013 | VinDr-Mammo | PhysioNet Restricted Health Data License 1.5.0 | registration | 2026-10-04 | WebFetch of PhysioNet project page | Access verified |
| IMG-014 | HAM10000 | CC-BY 4.0 (as reported on Sci Data descriptor page; Dataverse terms not fetched) | open | 2026-10-04 | Dataverse page and API blocked (robots.txt); WebFetch of Sci Data descriptor (nature.com/articles/sdata2018161) | Source verified |
| IMG-015 | ISIC Archive / ISIC 2019-2020 challenge | CC-BY-NC 4.0 (2019 and 2020 challenge data) | open | 2026-10-04 | WebFetch of ISIC challenge data page + isic-archive.com | Access verified |
| IMG-016 | PatchCamelyon (PCam) | CC0 (data); MIT (code) | open | 2026-10-04 | WebFetch of GitHub README | Access verified |
| IMG-017 | CAMELYON16 | Not reported | unknown | 2026-10-04 | WebFetch of challenge home, Data and Download pages | Source verified |
| IMG-018 | MedMNIST v2 / MedMNIST+ | CC BY 4.0 except DermaMNIST CC BY-NC 4.0; code Apache-2.0 | open | 2026-10-04 | WebFetch of medmnist.com + Zenodo record page (API blocked by robots.txt) | Access verified |
| IMG-019 | APTOS 2019 Blindness Detection | Not reported (competition rules not retrievable) | competition | 2026-10-04 | WebFetch of Kaggle overview/data pages (metadata only); Kaggle API returned 401 | Source verified |
| IMG-020 | IDRiD (Indian Diabetic Retinopathy Image Dataset) | Not reported | registration | 2026-10-04 | WebFetch of IEEE DataPort page | Access verified |
| PH-001 | WHO Global Health Observatory (GHO) OData API | Not reported on API page (WHO 'Terms of use' linked in footer) | open | 2026-10-04 | WebFetch of WHO GHO OData API docs page + live https://ghoapi.azureedge.net/api/Indicator?$top=3 (JSON) | Access verified |
| PH-002 | WHO Mortality Database | Non-commercial: 'no use will be made of them for commercial purposes'; WHO must be credited as source | open | 2026-10-04 | WebFetch of WHO Mortality Database landing page | Access verified |
| PH-003 | WHO/UNICEF Estimates of National Immunization Coverage (WUENIC) | Not reported (WHO Terms of use linked in footer) | open | 2026-10-04 | WebFetch of immunizationdata.who.int home + Download page | Access verified |
| PH-004 | CDC WONDER Underlying Cause of Death | Data use restrictions: 'Use these data for health statistical reporting and analysis only. Do not present or publish death counts of 9 or fewer...' | registration | 2026-10-04 | WebFetch of wonder.cdc.gov deaths-by-underlying-cause.html + ucd-icd10.html | Access verified |
| PH-005 | Behavioral Risk Factor Surveillance System (BRFSS) annual survey data | Not reported | open | 2026-10-04 | WebFetch of BRFSS annual data index + 2024 annual data page | Access verified |
| PH-006 | National Health and Nutrition Examination Survey (NHANES) | Not reported | open | 2026-10-04 | WebFetch of NHANES home, 2021-2023 cycle page, NHANES About page | Access verified |
| PH-007 | NNDSS Weekly Data | Not reported in metadata | open | 2026-10-04 | Socrata catalog API search + WebFetch of data.cdc.gov/api/views/x9gk-5huc.json | Access verified |
| PH-008 | PLACES: Local Data for Better Health, County Data, 2025 release | Public Domain | open | 2026-10-04 | Socrata catalog search + WebFetch of swc5-untb.json + cdc.gov/places | Parsed |
| PH-009 | NCHS - Leading Causes of Death: United States | Public Domain U.S. Government | open | 2026-10-04 | WebFetch of data.cdc.gov/api/views/bi63-dtpu.json | Parsed |
| PH-010 | National Family Health Survey (NFHS-5), 2019-21 | Not reported on page (OGD platform) | open | 2026-10-04 | WebFetch of data.gov.in NFHS-5 factsheet resource + DHS FR375 PDF; rchiips.org fetch failed (robots.txt) | Source verified |
| PH-011 | Health Management Information System (HMIS) India | Not reported (references NDSAP) | open | 2026-10-04 | Fetch failed for hmis.mohfw.gov.in (robots.txt ConnectTimeout); WebFetch of data.gov.in HMIS Bihar resource | Source verified |
| PH-012 | State/UT-wise Total Number of PHCs, SHCs and District Hospitals as per Rural Health Statistics (RHS) 2021-22 | Not reported (none shown) | open | 2026-10-04 | WebFetch of data.gov.in resource page | Source verified |
| PH-013 | IHME Global Burden of Disease (GBD) Results Tool | IHME FREE-OF-CHARGE NON-COMMERCIAL USER AGREEMENT (May 2020) | unknown | 2026-10-04 | Fetch failed for vizhub (403); WebFetch of ghdx gbd-2023/code, healthdata.org GBD page, IHME user agreement PDF | Access verified |
| PH-014 | Our World in Data COVID-19 dataset | Creative Commons BY license | open | 2026-10-04 | WebFetch of GitHub repo + public/data/README.md | Parsed |
| PH-015 | World Bank World Development Indicators (Health topic) | Creative Commons Attribution 4.0 | open | 2026-10-04 | WebFetch of WB Data Catalog WDI page + data.worldbank.org/topic/health + API overview | Parsed |
| PH-016 | CDC/ATSDR Social Vulnerability Index (SVI) | Not reported | open | 2026-10-04 | WebFetch of SVI landing + data download page | Source verified |
| PH-017 | EPA Air Quality System (AQS) / AirData | Not reported | open | 2026-10-04 | WebFetch of EPA outdoor air quality page, AirData download files page, AQS API docs | Access verified |
| PH-018 | DHS Program (Demographic and Health Surveys) | Terms of Use Statement required for GPS, HIV and biomarker datasets | registration | 2026-10-04 | WebFetch of dhsprogram.com/data and Access-Instructions page | Access verified |
| TS-001 | MIT-BIH Arrhythmia Database | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Parsed |
| TS-002 | PTB-XL, a large publicly available electrocardiography dataset | CC BY 4.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-003 | PTB Diagnostic ECG Database | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-004 | AF Classification from a Short Single Lead ECG Recording: The PhysioNet/Computing in Cardiology Challenge 2017 | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-005 | CHB-MIT Scalp EEG Database | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-006 | EEG Motor Movement/Imagery Dataset | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-007 | Sleep-EDF Database Expanded | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-008 | Temple University Hospital EEG Corpus (TUEG) and subsets | Not reported (data use agreement form required) | registration | 2026-10-04 | WebFetch of NEDC TUH EEG landing page | Access verified |
| TS-009 | BIDMC PPG and Respiration Dataset | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Parsed |
| TS-010 | MIMIC-III Waveform Database Matched Subset | Open Data Commons Open Database License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-011 | MIMIC-IV Waveform Database | Open Data Commons Open Database License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-012 | WESAD (Wearable Stress and Affect Detection) | Not reported on UCI page (refers to linked dataset for licensing) | unknown | 2026-10-04 | WebFetch of UCI landing page (UCI API endpoint returned unrelated dataset id 45) | Source verified |
| TS-013 | PPG-DaLiA | CC BY 4.0 | open | 2026-10-04 | WebFetch of UCI landing page (UCI API endpoint returned unrelated dataset id 45) | Access verified |
| TS-014 | Apnea-ECG Database | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-015 | CAP Sleep Database | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-016 | Cuff-Less Blood Pressure Estimation | CC BY 4.0 | open | 2026-10-04 | WebFetch of UCI landing page (UCI API endpoint returned unrelated dataset id 45) | Access verified |
| TS-017 | Non-EEG Dataset for Assessment of Neurological Status | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Parsed |
| TS-018 | Icentia11k Single Lead Continuous Raw Electrocardiogram Dataset | CC BY-NC-SA 4.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-019 | Early Prediction of Sepsis from Clinical Data: The PhysioNet/Computing in Cardiology Challenge 2019 | CC BY 4.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Access verified |
| TS-020 | A Wearable Exam Stress Dataset for Predicting Cognitive Performance in Real-World Settings | Open Data Commons Attribution License v1.0 | open | 2026-10-04 | WebFetch of PhysioNet project landing page | Parsed |
