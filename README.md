
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

## Synthetic data and augmentation (M5)

`ml/docsense_ml/synth/` generates Pakistani-style invoices with exact labels:
Faker + a custom provider (names, cities, NTN/STRN that pass the validators, PKR catalogue) fill six
HTML/CSS templates (thermal, FBR tax invoice, GST retail, POS compact, wholesale, Urdu-header service).
Playwright renders each page (system Edge, no browser download) and reads **region boxes, field boxes and
word boxes from the DOM**, so labels are exact by construction: classes `vendor, meta, table, totals, other`.
Generated invoices always satisfy the arithmetic/tax rules, which is asserted in tests.

Albumentations (bbox-aware) makes the renders look like phone photos: perspective, rotation, blur, noise,
JPEG, paper texture, creases, stains, shadows, low light, desk background, partial crops.

![Augmentation before/after](docs/images/augmentation.png)

```bash
PYTHONPATH=ml python -m docsense_ml.synth.build --out ml/data/synth --n 600 --aug full
PYTHONPATH=ml python -m docsense_ml.synth.preview      # regenerates the figure above
```

## Layout model, pipeline integration and active learning (M6-M8)

* **Training** (`ml/docsense_ml/layout/`): Ultralytics YOLO11n fine-tuned on the synthetic invoices with
  *our* Albumentations pipeline as the only augmentation (built-in mosaic/flip/HSV disabled so the ablation is
  clean). Every run is tracked in MLflow (`ml/runs/mlflow.db`). Experiments: **a** no aug, **b** basic aug,
  **c** full aug, **d** full aug + 30 real CORD receipts (human table/totals boxes + pseudo-labels for the rest).
  `python -m docsense_ml.layout.experiments --epochs 8 --imgsz 416`.
* **Real evaluation:** CORD-v2 test receipts with *table* and *totals* boxes derived from CORD's own word-level
  annotations (65 held-out receipts; 30 are used only for few-shot mixing in experiment d). CORD does not annotate
  vendor/meta/other: use `ml/tools/labeler.html` (offline, draw boxes, hotkeys) + `ml/tools/import_labels.py`
  to add your own real labels for those classes.
* **Pipeline:** `layout` step -> OCR words are assigned to regions -> the LLM sees `[VENDOR] [META] [TABLE]
  [TOTALS]` sections (footer truncated). If no table/totals is found the whole page is used (fallback).
  The detector is the active model from the registry, else `ml/models/layout-current.pt`, else disabled.
* **Active learning:** correct fields / draw layout regions on the review screen, approve ->
  a `TrainingSample` is stored. `manage.py retrain_layout --epochs 5 [--activate]` (or the Admin page button,
  staff only) fine-tunes the current model on approved documents, evaluates **old vs new** on synthetic-hard,
  CORD-real and a feedback holdout, and recommends activation only if nothing drops by more than 2 points.
  `manage.py activate_model <name>` / `--rollback` switch models.
