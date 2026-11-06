
## Pipeline (M2)

upload → cleanup (deskew/denoise/CLAHE) → OCR (docTR) → LLM fills `InvoiceExtraction` → rules in Python
(line math, subtotal, 18% tax, total, NTN/STRN, date) → per-field confidence → `done` or `needs_review`.
Live step progress over WebSocket (`/ws/documents/<id>/?token=<jwt>`).

Real OCR needs the ML extras: `pip install -r backend/requirements-ml.txt` (set `OCR_ENGINE=doctr`).
Real LLM: set `LLM_PROVIDER=groq`, `GROQ_API_KEY`, `GOOGLE_API_KEY` in `.env`.
Slow real-model tests: `pytest -m slow --force-enable-socket`.
