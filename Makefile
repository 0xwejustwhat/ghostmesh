.PHONY: install test lint format dev migrate

install:
	poetry install

test:
	poetry run pytest

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

dev:
	poetry run uvicorn ghostmesh.api.main:app --reload

migrate:
	poetry run alembic upgrade head

