# DocSense

**AI document intelligence for invoices and receipts.** Upload a PDF or a phone photo: DocSense cleans the
image, reads it with a local OCR engine, finds the invoice layout with a **YOLO model I trained myself on
synthetic Pakistani invoices**, has an LLM fill a strict schema from each region's text, then **checks the
result with rules written in code** (line math, 18% GST, NTN/STRN formats, dates). Fields it is unsure about
go to a review screen where corrections become training data. It also answers questions about your documents
with page-level citations (and says "not found" instead of guessing), analyses spending with a LangGraph agent
that can only run whitelisted read-only queries, flags duplicates and suspicious invoices, and draws every
document as a point in a 3D universe. Everything runs on free tiers (Groq + Gemini, local open-source models).

| Review screen | Spending analytics |
|---|---|
| ![Review](docs/images/review.jpg) | ![Analytics](docs/images/analytics.jpg) |

![Augmentation: clean render, basic, full](docs/images/augmentation.png)

> Placeholders for recordings: `docs/images/demo-upload.gif` (upload → live pipeline steps),
> `docs/images/demo-universe.gif` (3D universe), `docs/images/demo-chat.gif` (cited answers).

## Try it (one command)

```bash
cp .env.example .env            # optional: add GROQ_API_KEY / GOOGLE_API_KEY (free tiers)
docker compose up --build       # first build downloads the CPU ML stack (~3 GB)
```

Open http://localhost:5173 and sign in with the demo account **`demo@docsense.dev` / `docsense-demo-2025`**
(a public account on sample data). The first start migrates the database and seeds a **demo workspace with 50
sample documents** (planted duplicates, a price increase, an outlier, three documents waiting for review),
so every page has content with no API key, OCR run or LLM call. Uploading *new* documents needs a Groq or
Gemini key; browsing, reviewing, analytics, the universe, search retrieval and the evaluation page do not.

*Without Docker (Windows):* `scripts\dev-api.cmd` (SQLite, eager Celery, seeds the demo) and
`cd frontend && npm install && npm run dev`. `docker build --build-arg INSTALL_ML=0` gives a small image that
uses offline stand-ins (`OCR_ENGINE=fake EMBEDDER=hash RERANKER=overlap`).

> **Honesty note:** the Docker images, `docker compose up`, and the **pgvector search path** were written and
> statically validated (`docker compose config`; the pgvector tests are skipped on SQLite and run in CI against a
> pgvector Postgres service) but **I could not run them here**: the Docker engine would not start in the environment
> this was built in. Everything else below was run: the full backend natively on SQLite (including the real docTR,
> MiniLM, cross-encoder and YOLO models), the React app in a real browser against it, and all test suites.

## What is in it

| Area | What it does | Where |
|---|---|---|
| Pipeline | PDF/photo → deskew/denoise/CLAHE → docTR OCR → **my YOLO layout model** → text grouped by region → LLM (Groq, Gemini fallback, 429-aware backoff, cache) → Python validators → per-field confidence → `done` or `needs_review`; live progress over WebSocket | `backend/apps/pipeline`, `apps/validation`, `apps/llm` |
| Review + active learning | Field/box/line-item edits re-validate instantly; approve → invoice tables; drawn layout regions and corrections become `TrainingSample`s; `manage.py retrain_layout` / admin button fine-tunes and compares old vs new before activation | `apps/documents`, `apps/learning` |
| Ask your documents | Page- and bbox-preserving chunks, local MiniLM embeddings, pgvector ANN + BM25 → RRF → cross-encoder rerank; cited answers; abstains when the context lacks the answer (no LLM call if retrieval finds nothing) | `apps/rag` |
| Spending agent | LangGraph decide/tool loop; tools: structured **read-only** query (table/column whitelist, workspace filter injected in code, no SQL), chart-from-rows, price changes, doc search; UI shows every step and the rows used | `apps/agent` |
| Anomalies | exact/near/image duplicates, per-vendor robust z + IsolationForest, price creep, analytics page, executed methods notebook | `apps/analytics`, `ml/notebooks/02_anomaly_methods.ipynb` |
| 3D universe | UMAP → HDBSCAN → TF-IDF labels; one `InstancedMesh`; FPS monitor falls back to a 2D map | `apps/universe`, `frontend/src/components/Universe*` |
| Automation | HMAC-signed retrying webhooks with SSRF guard; API-key inbound endpoint; n8n workflow (email → DocSense → Sheets → Slack) | `apps/integrations`, `n8n/` |
| SaaS basics | JWT auth, workspaces with owner/member/viewer, hashed per-workspace API keys, upload quotas, rate limits, usage counters, staff admin (model registry, LLM usage) | `apps/accounts`, `apps/workspaces` |

```mermaid
flowchart LR
  subgraph Client
    UI[React + Vite + Tailwind<br/>review, chat, analytics, R3F universe]
    N8N[n8n: email → Sheets → alerts]
  end
  subgraph Backend[Django + DRF + Channels]
    API[REST: JWT + API keys]
    WS[WebSocket progress]
    ADM[Admin: models, LLM usage]
  end
  subgraph Workers[Celery]
    PIPE[pipeline task]
    RET[retrain job]
  end
  subgraph Pipeline
    CL[cleanup OpenCV] --> OCR[docTR]
    OCR --> LAY[YOLO layout<br/>my model]
    LAY --> GRP[group by region]
    GRP --> LLM[LLM → Pydantic schema]
    LLM --> VAL[Python validators + confidence]
    VAL -->|ok| DONE[(saved)]
    VAL -->|unsure| REV[(review queue)]
  end
  LLMS[Groq → Gemini fallback]
  PG[(PostgreSQL + pgvector)]
  RD[(Redis)]
  UI <--> API
  UI <--> WS
  N8N <--> API
  API --> PIPE --> Pipeline
  PIPE --> WS
  LLM -.-> LLMS
  Pipeline --> PG
  API --> PG
  API --> RD
  REV --> RET
  RET --> LAY
```

## Evaluation

Every number below is produced by a script in this repo (`docs/eval-results/*.json` →
`python scripts/readme_tables.py`) and is also shown on the app's **Evaluation** page.

<!-- results:start -->

#### Layout model (mAP@50, IoU 0.5)

| Experiment | Synthetic (hard) mAP@50 | Real CORD mAP@50 | real: table | real: totals |
|---|---|---|---|---|
| **exp-a**: synthetic, no augmentation | 49.3% | **6.8%** | 10.5% | 3.0% |
| **exp-b**: synthetic, basic augmentation | 84.7% | **15.2%** | 12.2% | 18.1% |
| **exp-c**: synthetic, full augmentation | 98.5% | **14.4%** | 14.1% | 14.8% |
| **exp-d**: full augmentation + 30 real receipts (few-shot mix) | 97.9% | **58.8%** | 54.3% | 63.3% |
| **exp-e**: full augmentation + scene placement (page small on a table/hand) | 86.6% | **22.7%** | 26.6% | 18.8% |
| **exp-f**: scene augmentation + 30 real receipts (few-shot mix) | 88.1% | **70.7%** | 67.2% | 74.1% |

Per-class AP@50 on the synthetic hard set (60 images, all five classes):

| Experiment | vendor | meta | table | totals | other |
|---|---|---|---|---|---|
| exp-a | 73.4% | 31.7% | 72.5% | 31.8% | 37.2% |
| exp-b | 86.2% | 81.5% | 96.9% | 90.1% | 68.9% |
| exp-c | 99.2% | 99.5% | 99.5% | 98.5% | 95.8% |
| exp-d | 98.4% | 99.5% | 99.5% | 98.8% | 93.4% |
| exp-e | 91.0% | 77.7% | 97.2% | 89.0% | 78.2% |
| exp-f | 93.4% | 85.8% | 97.7% | 85.4% | 78.4% |

#### Field extraction (OCR + extractor)

| Dataset | Arm | N | Micro F1 | Total exact-match | line-item F1 |
|---|---|---|---|---|---|
| cord | regex | 95 | 67.4% | 63.2% | 25.3% |
| cord-v2 (65 held-out receipts) | regex + my layout model (fields restricted to their region) | 65 | 59.1% | 53.8% | 23.3% |
| cord-v2 (65 held-out receipts) | regex + my layout model | 65 | 66.1% | 61.5% | 23.3% |
| cord-v2 (65 held-out receipts) | regex | 65 | 66.4% | 63.1% | 21.6% |

Per-field (CORD, regex):

| Field | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| subtotal | 95.2% | 62.5% | 75.5% | 64 |
| sales_tax | 95.5% | 51.2% | 66.7% | 41 |
| total | 63.2% | 63.2% | 63.2% | 95 |

#### Ask your documents (RAG)

| Setup | Questions | Hit@5 | MRR | Unanswerable rejected by retrieval gate | Judge (1-5) | Citation accuracy | Abstention accuracy |
|---|---|---|---|---|---|---|---|
| retrieval \| all-MiniLM-L6-v2 + ms-marco-MiniLM-L-6-v2 | 48 | 100.0% | 0.85 | 83.3% | pending (needs API keys) | pending | pending |

_Generated by `python scripts/readme_tables.py` from `docs/eval-results/*.json`._
<!-- results:end -->

### The synthetic-to-real gap (layout model)

The layout model is trained only on synthetic invoices (600 rendered from six Pakistani-style templates, labels
read from the DOM so they are exact) and tested two ways: a **hard synthetic set** (60 images with phone-photo
augmentation, all five classes) and **65 held-out real receipts from CORD** (only *table* and *totals* have real
annotations; the other three classes cannot be scored on real data). Six experiments, one seed each, YOLO11n,
416 px, 8 epochs, CPU, tracked in MLflow:

| | what changes | synthetic (hard) | **real** |
|---|---|---|---|
| a | no augmentation | 49.3% | 6.8% |
| b | + geometry, blur, noise, JPEG | 84.7% | 15.2% |
| c | + paper texture, shadows, creases, stains, low light, desk background, crops | 98.5% | 14.4% |
| d | c + **30 real receipts** (human table/totals boxes; model pseudo-labels for the other classes) | 97.9% | **58.8%** |
| e | c + *scene placement*: page small on a table/hand | 86.6% | 22.7% |
| f | e + the same 30 real receipts | 88.1% | **70.7%** |

**What the numbers say**

1. **Augmentation is what makes a synthetic detector usable at all on synthetic photos** (49% → 98%), and without
   it the photometric classes (meta, totals, other) collapse. But a 98.5% synthetic score says almost nothing
   about real receipts: all three synthetic-only models are at 7-15% real mAP@50. b and c are within noise of each
   other on 65 images, so I would not claim the extra photometric effects in c help on real data.
2. **The failure is scale and context, not just texture.** On real photos the detector's boxes are faint, wide
   bands in the wrong places (`docs/images/real_gap_exp_c.png`): real receipts are narrow strips occupying a third
   of the frame on tables, laps and hands, while my synthetic pages fill the frame. Placing the page on a larger
   textured surface (e) raised real mAP from 14.4% to 22.7%, a real but partial fix, and cost accuracy on the
   full-frame synthetic validation set (98.5% → 86.6%): the two distributions pull in different directions.
3. **A few real labels beat any amount of synthetic augmentation I tried**: mixing 30 real receipts (oversampled 3x)
   lifts real mAP from 14.4% to 58.8% (d) while the synthetic score is unchanged (97.9%), and combined with scene
   placement reaches 70.7% (f, the model that ships). The gallery for d (`docs/images/real_gap_exp_d.png`) shows
   totals boxes landing on the right lines.

**Caveats I would not skip**

* The 30 mixed receipts and the 65 test receipts come from the *same dataset* (same cameras, same kinds of
  shops; disjoint receipts). So d/f overstate how well this transfers to other real receipts. Some of the gain is
  also the model learning CORD's **annotation convention** (its "totals" box includes cash and change lines),
  which I did not separate from genuine visual adaptation.
* Only table and totals are measurable on real data. Vendor/meta/other on real receipts are unmeasured; the
  pseudo-labels used for them in d/f come from the synthetic model and were never checked by a human.
* 65 test images, one seed, a nano model, 8 epochs: individual AP values carry wide uncertainty. Choosing f over
  d used the same 65 receipts I report on, a mild optimistic bias.
* No real Pakistani invoices were available; Indonesian restaurant/retail receipts are a proxy.

**Does the layout model improve extraction?** Not measurably, in the one place I could test it without an API
key. Same 65 real receipts, same docTR OCR, same heuristic extractor, with and without my layout model:

| | micro F1 | total exact match | prompt tokens/doc |
|---|---|---|---|
| whole page | 66.4% | 63.1% | 48 |
| layout model, fields **restricted** to their region | 59.1% | 53.8% | 55 |
| layout model, region as a prior (whole-page fallback) | 66.1% | 61.5% | 55 |

Hard-restricting each field to its predicted region *hurts* (a box that cuts off the total line loses it); using
regions only as a prior removes the damage but gives no gain, and the marked-up prompt is slightly longer on
these short receipts. The expected benefit (a cleaner, shorter, better-structured LLM prompt) is a hypothesis
for the LLM arm, which I could not run without a Groq/Gemini key. I would not claim it until that number exists.

### Active learning, tested end to end (and what it showed)

I approved the demo workspace's three review-queue documents (fixing their totals and confirming the layout), then
ran the real `manage.py retrain_layout --epochs 1`: export the approved documents → fine-tune the shipped model →
evaluate old and new on the *same* sets → register a `ModelVersion` with the deltas → recommend activation only if
no set drops by more than 2 points. Three recipes, same 3 documents:

| Retrain recipe | synthetic (hard) | real CORD | verdict |
|---|---|---|---|
| fine-tune on full-frame synthetic + feedback | 88.1% → 58.6% | 70.7% → 1.8% | not recommended |
| + replay of the real receipts and scene data | 88.1% → 96.4% | 70.7% → 44.9% | not recommended |
| replay of exactly the base model's recipe + feedback | 88.1% → 83.1% | 70.7% → 56.8% | not recommended |

The safety gate did its job (it blocked three harmful updates; none was activated), and the first run exposed a
real flaw in my first recipe (catastrophic forgetting of the real-receipt adaptation) that the later recipes
reduced but did not remove. Three approved documents are far too little signal to improve an already-tuned
model; the loop needs a lower learning rate or frozen backbone and tens of approved documents before it will
recommend an activation. I did not tune further, so treat active learning as **working mechanics plus a
working guard, not yet a demonstrated accuracy gain**.

### Reproduce

```bash
python -m docsense_ml.cord --out ml/data/cord                         # CORD-v2 test split (CC BY 4.0, ~234 MB)
python -m docsense_ml.layout.real                                     # table/totals boxes from CORD's own annotations
python -m docsense_ml.synth.build --out ml/data/synth --n 600         # 3 augmentation levels, DOM-exact labels
python -m docsense_ml.layout.make_scene_dataset                       # experiment e/f data
python -m docsense_ml.layout.experiments --epochs 8 --exps a,b,c,d,e,f   # MLflow: ml/runs/mlflow.db
python -m docsense_ml.evaluate --set ml/data/cord --arm regex --idr   # extraction baseline (or --arm llm)
python manage.py eval_rag                                             # retrieval; add --answer-provider/--judge-provider
python manage.py import_eval && python scripts/readme_tables.py
```

## Free-tier design

Small prompts (OCR text per region, footer truncated), local embeddings/rerank/OCR/YOLO/UMAP, LLM responses cached
by prompt hash, retry/backoff that honours `retry-after` then fails over from Groq to Gemini, paced evaluation calls,
a retrieval gate that skips the LLM when nothing relevant was found, and an admin page counting requests, 429s,
cache hits and estimated tokens per provider. Only demo/synthetic data should go to the free APIs.

## Tests

Backend (pytest, offline: `FakeChatModel`, hash embedder, sockets blocked to loopback): auth/permission matrix,
tenant isolation, validators, pipeline, review, RAG, agent query safety (injection, workspace scope, SELECT-only),
anomaly detectors, webhooks (signing, SSRF, retries), seed, evaluation. `ml/` (metrics, generators, augmentation,
layout tooling) and frontend (Vitest) have their own suites. Slow tests (real docTR, real MiniLM, real browser
rendering, Postgres) are marked and run with `pytest -m slow --force-enable-socket`. CI: ruff + pytest (with a
pgvector Postgres service), eslint + vitest + build, ml tests.

```bash
make test && make lint
```

## Licences and data

* **CORD-v2** (Naver Clova): CC BY 4.0, Park et al. 2019. Downloaded by script, not redistributed here.
  SROIE was **not** used (no clear open licence).
* **Ultralytics YOLO** is AGPL-3.0: fine for this open repo; a closed product would need a commercial licence
  or another detector. docTR (Apache-2.0), sentence-transformers/MiniLM and the MS-MARCO cross-encoder (Apache-2.0).
* The demo documents are synthetic. Repo code: MIT.

## What I would improve next

1. **LLM-arm numbers.** I had no Groq/Gemini key while building, so extraction F1 and RAG answer quality (judge,
   citation accuracy) are measured only for the no-LLM baseline and for retrieval. The harness is ready
   (`make eval-cord-llm`, `manage.py eval_rag --answer-provider groq --judge-provider gemini`).
2. **Real Pakistani invoices.** None were available, so the real-data layout evidence is CORD (Indonesian
   thermal receipts, only table/totals annotated). Label ~100 real invoices with `ml/tools/labeler.html` to
   measure vendor/meta/other and to fine-tune for the target domain.
3. **Receipt localisation before layout.** Detect the paper quadrilateral and rectify it, then run the layout
   model on the crop; combined with scene augmentation this should reduce the need for real labels.
4. **Digital-PDF text layer** to skip OCR when text is embedded; a local small VLM as an offline extractor.
5. **Urdu OCR** (PaddleOCR via the existing OCR adapter) so Urdu shop names are read, not just tolerated.
6. Streaming agent steps (SSE), per-field calibration of the confidence weights (reliability curve), a hosted
   deployment (Vercel + Render + Neon) with a worker, and verifying the n8n export on a live instance.

## Layout of the repo

```
backend/   Django apps: accounts workspaces documents pipeline validation llm rag agent analytics
           universe learning integrations evaluation common
frontend/  React + Vite + Tailwind + React Three Fiber
ml/        docsense_ml: synth (generator, templates, augmentation), layout (train, eval, retrain), metrics,
           CORD loader, baselines, notebooks/, tools/labeler.html
n8n/       workflow export + generator + README
seed/      demo_workspace/ (50 synthetic documents with word/region/field boxes)
eval/      rag_questions.yaml (48 questions, extendable)
docs/      eval-results/, images/
```

See [PLAN.md](PLAN.md) for the original plan and the list of deviations from it.
