# DocSense

AI document intelligence for invoices and receipts (Django · React · LangGraph · YOLO · pgvector).
See [PLAN.md](PLAN.md) for the full roadmap. Status: **M0 – foundations**.

## Run

```bash
cp .env.example .env
docker compose up --build   # api :8000, frontend :5173, mlflow :5000
```

Local dev without Docker: `cd backend && python -m venv .venv && pip install -r requirements-dev.txt && python manage.py runserver`, then `cd frontend && npm i && npm run dev`.

## Test & lint

```bash
make test && make lint
```

Tests run fully offline (LLM calls use `FakeChatModel`; sockets are blocked by pytest-socket).
