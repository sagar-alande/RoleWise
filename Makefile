.PHONY: up down migrate test lint evals

up:
	docker compose up --build

down:
	docker compose down

migrate:
	docker compose exec api alembic upgrade head

test:
	cd apps/backend && pip install -e ".[dev]" -q && pytest

lint:
	cd apps/backend && ruff check .
	cd apps/web && npm install --silent && npm run typecheck

evals:
	cd apps/backend && python ../../evals/run_matching_eval.py
