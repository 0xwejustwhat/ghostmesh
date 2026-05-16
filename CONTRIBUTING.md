# Contributing

Thanks for helping build Ghost Mesh.

## Development

```bash
poetry install
poetry run ruff check .
poetry run pytest
```

Poetry is the required dependency and packaging workflow.

## Pull Requests

- Keep changes scoped.
- Add or update tests for behavior changes.
- Update documentation when public behavior changes.
- Do not commit generated caches or local database state.
- Preserve the rule that workers are pipe-aware and Patch Panels own routing.

## Local Stack

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

## Code Style

Ruff is the source of truth for linting and formatting.
