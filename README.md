# Generic Experimental Data Import — React + FastAPI add-on

This add-on accepts CSV files, or ZIP archives containing **exactly one CSV**. It preserves the existing MITM archive workflow and adds a separate descriptive evaluation path for normalized data.

## Files

- `App.jsx` — the original application with a mode switch for Generic CSV/ZIP vs Existing MITM Archive.
- `GenericImportPanel.jsx` — upload, suggested column mapping, manual overrides, preview, validation, descriptive evaluation and normalized CSV download.
- `generic_import.py` — an independent FastAPI router providing the generic endpoints.
- `tests/test_generic_import.py` — six backend integration tests.
- `example_experiments.csv` — a sample generic dataset.

## Integrate into the existing project

1. Put `App.jsx` and `GenericImportPanel.jsx` beside the existing `styles.css` and use `App.jsx` in place of the old app entrypoint. Keep the original dependencies, including `react`, `react-dom` and `lucide-react`.
2. Copy `generic_import.py` into the backend package (or adjust its import path).
3. In the existing FastAPI setup, **include** the router (do not replace the app):

```python
from generic_import import generic_router
app.include_router(generic_router)
```

   If copying into the `claim_auditor/` package, use:

```python
from claim_auditor.generic_import import generic_router
app.include_router(generic_router)
```

4. Continue running Uvicorn with your existing command and use the React frontend on the same origin or configure the development proxy to forward `/api/v1` to the backend.
5. Required server packages: `fastapi`, `pydantic`, `python-multipart`, plus your existing Uvicorn environment.
6. Verify: `python -m unittest discover -s tests -v` (run the six tests from within this package with its Python path available).

## Generic CSV required columns (names can be mapped)

| Canonical field | Meaning |
| --- | --- |
| `dataset_id` | Dataset identity |
| `protocol_id` | Evaluation protocol/preprocessing context identity |
| `target_class` | Positive class/attack label |
| `split_id` | Evaluation split or fold identifier |
| `method` | Model or method name |
| `recall` | Numerical fraction from 0 to 1 |
| `fpr` | Numerical fraction from 0 to 1 |

The UI guesses common aliases but lets users map arbitrary column names manually. Data must be numeric fractions, not percentage strings (for example `0.95`, not `95%`). Each row represents one method on one evaluation split.

## API

- `POST /api/v1/generic/preview` (multipart `file`) — returns column names, mapping suggestions and sample records.
- `POST /api/v1/generic/import` (JSON `preview_id`, `mapping`, `comparison_metadata_confirmed`) — validates and saves normalized data.
- `POST /api/v1/generic/evaluate` — paired descriptive recall comparison under an FPR limit.
- `GET /api/v1/generic/imports/{import_id}/csv` — download normalized CSV.

## Scientific safeguards and known limitations

This **is a working prototype add-on**, not a verified integration into the full original backend, which was not supplied. The generic evaluation endpoint is intentionally separate from the original MITM evaluation and does not attempt to reuse internal auditor models without their source code.

- Comparisons are scoped to the **same dataset, protocol, target class, and split ID**; methods must be distinct.
- These identifiers alone cannot prove equal test populations, preprocessing, data leakage freedom, session independence, or true comparability. The user can explicitly affirm metadata compatibility; a warning remains that statistical superiority is not established.
- Splits with only one method are reported as `MISSING_PAIR`. Splits where either method violates the selected FPR are reported `FPR_INFEASIBLE`.
- The reported `OBSERVED_CONDITIONAL_SUPPORT` is a **descriptive label only** and is NOT statistical significance or superiority.
- ZIP must contain exactly one CSV, with no arbitrary scripts run; 8 MiB upload cap, 24 MiB uncompressed cap, 100k-row cap.
- Local prototype: storage is filesystem-based and has **no authentication, persistence controls, or production security hardening**. Do not expose publicly. Preview/upload cleanup and retention policies are not implemented.
- No formal benchmark, advanced significance testing, random-effects analysis, or model training.

## Test

```bash
python -m unittest discover -s tests -v
```
