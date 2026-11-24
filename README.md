# ML Research Claim Auditor

**A research-oriented web application for auditing machine-learning experimental evidence and assessing descriptive performance claims under operational constraints.**

ML Research Claim Auditor helps researchers import evaluation results, check their structure, compare methods on matched experimental splits, and produce traceable reports. It explicitly distinguishes **observed descriptive support** from **verified methodological comparability** and **statistical superiority**.

> **Research prototype:** A successful audit is not a statistical significance test, proof of causal superiority, or independent verification of the underlying experimental data.

## Features

- **Generic experimental data import:** Upload a CSV, or a ZIP containing exactly one CSV. Preview the source, map column names, validate records, and download normalized data.
- **Descriptive claim evaluation:** Compare a baseline and challenger within the same dataset, protocol, target class, and split identifiers. Set a maximum test false-positive rate (FPR) and inspect recall differences, feasible splits, wins, losses, and ties.
- **Experimental comparability assessment:** Supply optional documented metadata for both methods. The tool reports `DECLARED_COMPATIBLE`, `UNVERIFIED`, or `INCOMPATIBLE`; matching declarations are **not** independent verification.
- **Scientific claim status:** Distinguishes descriptive findings from methodological status using labels such as `NOT_VERIFIED`, `BLOCKED_INCOMPATIBLE`, and `DESCRIPTIVE_SUPPORT_ONLY`.
- **Existing MITM archive workflow:** Import supported corrected or stability experiment archives, inspect evidence integrity, evaluate claims, and export audit evidence.
- **Regression checks:** Compare the original MITM audit implementation with the generic import path using the same supplied archives and target FPR.
- **Reports:** Download Markdown research-claim or regression reports and available CSV/JSON evidence exports.

## Live demo

- **Frontend:** https://ml-research-claim-auditor.vercel.app/
- **Backend health endpoint:** https://ml-research-claim-auditor-api.onrender.com/api/v1/health

The demo is protected using HTTP Basic authentication. Access is provided only to authorized users with separate **demo credentials**. Authentication is configured using environment variables on Vercel and Render. Sensitive credentials are not stored in the repository.

The hosted prototype is not designed for sensitive, confidential, or unlicensed uploads. Storage is filesystem-based and may be ephemeral on the hosting platform. A shared demo login is **not** per-user data isolation.

## Architecture

| Layer | Technology | Purpose |
| --- | --- | --- |
| Frontend | React, Vite, Lucide React | Data import, audit controls, results and reports |
| Backend | Python, FastAPI, Uvicorn | Validation, evaluation, regression checks and exports |
| Frontend hosting | Vercel | Static web app and `/api` proxy |
| Backend hosting | Render | FastAPI web service |
| Version control | GitHub | Source code and deployment integration |

The frontend sends requests to `/api/v1/...`. During local development, Vite proxies these requests to `http://127.0.0.1:8001`. In the hosted deployment, Vercel forwards `/api/...` to the Render service. Both the public frontend and direct backend access require authentication outside the public health-check endpoint.

## Getting started locally

### Prerequisites

- A recent Node.js version compatible with the project's installed Vite release (check `package.json` and Vite's current requirements).
- Python and `venv` support. The project has been run locally using Python 3.10; the deployment configuration can specify a different compatible version.
- npm.

### Install dependencies

```bash
# From the repository root
npm ci

python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### Run the API

```bash
.venv/bin/python -m uvicorn claim_auditor.api:app --host 127.0.0.1 --port 8001
```

Open a **second terminal** and run the frontend:

```bash
npm run dev
```

Vite prints its local development URL (usually `http://localhost:5173`). By default, local development does not require demo credentials when `APP_ENV` is not `production`.

### Run tests and build

```bash
.venv/bin/python -m unittest discover -s tests -v
npm run build
```

In the November 2026 local verification, **14 Python tests passed**. An MITM regression run using corrected and stability archives reported **8/8 passing implementation-consistency comparisons** (4 per protocol). These results reflect the tested versions and input archives; rerun tests after changes.

## Generic CSV schema

Column names can be mapped manually in the UI.

| Canonical field | Meaning |
| --- | --- |
| `dataset_id` | Dataset identifier |
| `protocol_id` | Evaluation protocol identifier |
| `target_class` | Positive class / attack label |
| `split_id` | Evaluation split, fold, or seed identifier |
| `method` | Model or experimental method |
| `recall` | Recall as a fraction from `0` to `1` |
| `fpr` | False-positive rate as a fraction from `0` to `1` |

Each row represents one method on one defined split. Metrics must be finite numerical fractions, not percentage strings. Matching split identifiers alone do not establish matched test populations, independent folds, or comparable preprocessing.

Example:

```csv
dataset_id,protocol_id,target_class,split_id,method,recall,fpr
sample_dataset,sample_protocol,positive,1,baseline,0.90,0.01
sample_dataset,sample_protocol,positive,1,challenger,0.92,0.01
```

**Import limits:** Generic ZIP files must contain exactly one CSV; current import limits include an 8 MiB uploaded archive/file size cap, a 24 MiB uncompressed size cap, and a 100,000-row limit. These limits do not replace operational rate limiting or storage retention controls.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Service health check |
| `POST` | `/api/v1/generic/preview` | Preview a generic CSV/ZIP upload |
| `POST` | `/api/v1/generic/import` | Validate and import mapped records |
| `POST` | `/api/v1/generic/evaluate` | Run a descriptive paired evaluation |
| `GET` | `/api/v1/generic/imports/{import_id}/csv` | Export normalized records |
| `POST` | `/api/v1/datasets/import` | Import a supported original MITM archive |
| `POST` | `/api/v1/claims/evaluate` | Evaluate an original MITM claim |
| `GET` | `/api/v1/audits/{audit_id}/report` | Download a Markdown audit report |
| `GET` | `/api/v1/audits/{audit_id}/evidence` | Download audit evidence |
| `POST` | `/api/v1/regression/run` | Compare the MITM and generic audit paths |

The regression route accepts the **corrected** and **stability** ZIP archives and a target FPR. For full request/response details, inspect the FastAPI route definitions and the locally available `/docs` endpoint.

## Deployment

### Render (FastAPI)

The repository contains a `render.yaml` Blueprint configuration. The application is launched with Uvicorn and listens on the port supplied by Render.

Set the following **server-side environment variables** in Render:

| Variable | Purpose |
| --- | --- |
| `APP_ENV=production` | Enable backend demo authentication |
| `DEMO_USERNAME` | Demo username |
| `DEMO_PASSWORD` | Demo password |
| `PYTHON_VERSION` | Selected supported Python runtime, if configured |

The backend must reject protected API requests without credentials; the health endpoint may remain public for platform health checks.

### Vercel (React + Vite)

Build using `npm run build` and publish the `dist` directory. The repository's Vercel configuration proxies `/api` to the backend. The Vercel middleware protects the app and uses **server-side** `DEMO_USERNAME` and `DEMO_PASSWORD` environment variables.

Use HTTPS. Do not expose secrets in `VITE_` variables or frontend source files. Verify that authentication applies to both page requests and API requests after every deployment, including direct Render access.

## Scientific interpretation and limitations

- **Descriptive, not inferential:** `OBSERVED_CONDITIONAL_SUPPORT` reports an observed outcome under the supplied constraints, not statistical significance or superiority.
- **FPR constraint:** Only jointly feasible method pairs contribute to feasible win/loss/tie counts. Missing pairs and FPR-infeasible splits are explicitly reported.
- **Comparability metadata:** `DECLARED_COMPATIBLE` means required *supplied* metadata agree. It does not establish provenance, label correctness, leakage freedom, or statistical independence.
- **Independence:** Repeated splits or cross-validation folds may have overlapping samples; they must not automatically be treated as independent experiments.
- **Protocols:** Corrected and stability protocols should be interpreted separately unless a separate, defensible comparability analysis is performed.
- **Regression checks:** Passing comparisons establish consistency between tested software paths for the given evidence, not the correctness of ground truth or research originality.
- **No model training:** The auditor consumes external experimental results; it does not train or benchmark ML models itself.
- **Deployment constraints:** Local/ephemeral storage, a shared demo account, and the absence of formal per-user isolation and retention controls limit suitable deployment uses.

### Research data and citations

For any published work using ToN-IoT, IoTID20, UCI Wine, or other datasets, cite the **original dataset publications** and comply with each dataset's terms. The repository does not assert redistribution rights over third-party raw datasets. Example CSVs and test fixtures should be reviewed before public distribution.

## Repository hygiene

Keep `.venv/`, `node_modules/`, build artifacts, environment files, temporary imports, local storage, and credentials out of Git. Review any proposed test data or ZIP archives before adding them to version control. A `.gitignore` file is not a substitute for checking Git history for accidentally committed secrets.

## Author

**Sandra Ristić**  
Research and development - ML Research Claim Auditor

## Project status

**Research prototype / early demo release.** The working app has passed the reported functional tests, but it has not undergone an independent security audit, a comprehensive scientific validation, or a confirmed novelty assessment against the research literature.