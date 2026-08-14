.PHONY: up down api-test api-seed api-dev web-dev
up:
	docker compose up --build

down:
	docker compose down

api-test:
	cd apps/api && pytest

api-seed:
	cd apps/api && python -m app.db.seed

api-dev:
	cd apps/api && uvicorn app.main:app --reload --port 8000

web-dev:
	cd apps/web && npm run dev
