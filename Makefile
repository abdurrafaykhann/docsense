.PHONY: up down test lint fmt
up:
	docker compose up --build
down:
	docker compose down
test:
	cd backend && python -m pytest
	cd ml && python -m pytest
	cd frontend && npm test
lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint && npm run format:check
fmt:
	cd backend && ruff format . && ruff check --fix .
	cd frontend && npm run format

eval-cord-regex:
	PYTHONPATH=ml python -m docsense_ml.evaluate --set ml/data/cord --arm regex --idr
eval-cord-llm:
	PYTHONPATH=ml python -m docsense_ml.evaluate --set ml/data/cord --arm llm --provider groq --idr
