
## Pipeline (M2)

upload → cleanup (deskew/denoise/CLAHE) → OCR (docTR) → LLM fills `InvoiceExtraction` → rules in Python
(line math, subtotal, 18% tax, total, NTN/STRN, date) → per-field confidence → `done` or `needs_review`.
Live step progress over WebSocket (`/ws/documents/<id>/?token=<jwt>`).

Real OCR needs the ML extras: `pip install -r backend/requirements-ml.txt` (set `OCR_ENGINE=doctr`).
Real LLM: set `LLM_PROVIDER=groq`, `GROQ_API_KEY`, `GOOGLE_API_KEY` in `.env`.
Slow real-model tests: `pytest -m slow --force-enable-socket`.

## Evaluation (M4)

`ml/` holds the offline harness (`python -m docsense_ml.evaluate`). It runs the *same* pipeline code as
the app (`apps/pipeline/core.py`) over a labelled set and reports field-level precision/recall/F1,
exact-match rate for totals, review-routing metrics and prompt tokens per document. Results are written
to `docs/eval-results/*.json`, loaded with `manage.py import_eval`, and shown on the in-app Evaluation page.

**Dataset:** CORD-v2 test split (95 receipts with a total), Naver Clova, licence **CC BY 4.0**
(Park et al., 2019). Not redistributed in this repo: `python -m docsense_ml.cord` downloads it (~234 MB).
CORD receipts are Indonesian (IDR, ~10% PPN) and annotate only line items, subtotal, tax and total, so
vendor/date/NTN/STRN are not scored on it.

### Baseline: regex heuristics + docTR OCR (no LLM) - commit `docs/eval-results/cord-regex.json`

| Field | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| total | 63.2% | 63.2% | 63.2% | 95 |
| subtotal | 95.2% | 62.5% | 75.5% | 64 |
| sales_tax | 95.5% | 51.2% | 66.7% | 41 |
| line items (amount + description) | 32.2% | 20.9% | 25.3% | 235 |
| **micro (scalar fields)** | 76.1% | 60.5% | **67.4%** | 200 |

Total exact-match: **63.2%**. This is the floor the LLM arm (`make eval-cord-llm`, needs `GROQ_API_KEY`)
and the layout model (M7) must beat. **LLM-arm numbers are not in yet** (no API key was configured when
this was run). Routing metrics (review rate / errors caught) are not meaningful on CORD because every
CORD document lacks the required vendor/date fields, so they are reported on the synthetic and own sets.
