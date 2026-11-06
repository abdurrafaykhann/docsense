.PHONY: up down test lint fmt
up:
	docker compose up --build
down:
	docker compose down
test:
	cd backend && python -m pytest
	cd frontend && npm test
lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint && npm run format:check
fmt:
	cd backend && ruff format . && ruff check --fix .
	cd frontend && npm run format
