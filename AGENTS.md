# AGENTS.md

You are an expert Python backend engineer working on a **Clean Architecture image processing microservice** built with FastAPI, SQLAlchemy 2.0 (async), and PostgreSQL.

## Commands

```bash
# Run all tests (no external services needed — everything is mocked)
pytest -v

# Run tests with coverage
pytest --cov=src --cov-report=term-missing

# Type checking
mypy src/

# Lint and auto-fix
ruff check src/ tests/ --fix

# Format code
ruff format src/ tests/

# Build and run with Docker Compose
docker compose up --build

# Build C++ extension (optional)
cd cpp && bash build.sh

# Start dev server (requires running PostgreSQL)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## Tech Stack

- **Python** ≥3.11 (Docker uses 3.12)
- **FastAPI** ≥0.115 with Uvicorn ≥0.34
- **SQLAlchemy** ≥2.0 (fully async with asyncpg ≥0.30)
- **PostgreSQL** 16
- **Pillow** ≥11.0 for image processing
- **Pydantic** ≥2.0 with pydantic-settings ≥2.0
- **Ruff** for linting/formatting (line-length: 100, target: py311)
- **mypy** ≥1.13 (strict mode)
- **pytest** ≥8.0 with pytest-asyncio (asyncio_mode = "auto")

## Architecture (Clean Architecture — 4 Layers)

The codebase follows strict **Clean Architecture** with four layers under `src/`:

| Layer | Location | Purpose |
|---|---|---|
| **Domain** | `src/domain/` | Pure business logic, entities, abstract ports (ABC). ZERO external deps. |
| **Application** | `src/application/` | Use cases and frozen-dataclass DTOs. Depends only on Domain. |
| **Infrastructure** | `src/infrastructure/` | Concrete adapters: PostgreSQL repository, Pillow processor, filesystem storage. |
| **Presentation** | `src/presentation/` | FastAPI routes, Pydantic schemas, middleware, DI wiring. |

Tests mirror this structure under `tests/` (domain, application, infrastructure, presentation).

**Dependency rule**: Dependencies point inward only. Domain has no imports from other layers. Application depends only on Domain. Infrastructure and Presentation implement Domain interfaces.

**Key domain concepts**: `Image` entity with `ProcessingStatus` (PENDING → PROCESSING → COMPLETED | FAILED), `RetentionPolicy` for tag-based TTL cleanup, three abstract ports (`ImageRepository`, `ImageStorage`, `ImageProcessor`).

## Code Style

**Line length**: 100 characters. **Ruff rules**: E, F, I, N, W, UP, B, SIM, RUF.

**Naming**: PascalCase for classes, snake_case for functions/variables, UPPER_SNAKE_CASE for constants.

Use full type hints everywhere. Use `from __future__ import annotations` for forward references.

```python
# ✅ Good — typed, async, uses domain abstractions
class ProcessImageUseCase:
    def __init__(
        self,
        repository: ImageRepository,   # Abstract port, not concrete class
        storage: ImageStorage,
        processor: ImageProcessor,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._processor = processor

    async def execute(self, image_id: uuid.UUID) -> ImageResponseDTO:
        image = await self._repository.get_by_id(image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        ...
```

```python
# ❌ Bad — importing concrete implementations in domain layer
from src.infrastructure.database.models import ImageModel  # NEVER in domain/

# ❌ Bad — missing type hints, mutable DTO
class ImageDTO:
    def __init__(self, id, filename):
        self.id = id
        self.filename = filename
```

## Testing

Tests require no external services. All infrastructure is mocked via `AsyncMock` specs.

```bash
# Run specific test layers
pytest tests/domain/ -v          # Pure unit tests
pytest tests/application/ -v     # Use case tests
pytest tests/infrastructure/ -v  # Adapter tests (real Pillow, temp directories)
pytest tests/presentation/ -v    # API tests with TestClient
```

Fixtures in `tests/conftest.py` provide: `sample_image_bytes`, `sample_image_entity`, `completed_image_entity`, `mock_repository`, `mock_storage`, `mock_processor`.

When writing tests:
- `pytest.mark.asyncio` is automatic (asyncio_mode = "auto")
- Mock at the port boundary (use `AsyncMock(spec=ImageRepository)`)
- Infrastructure tests use real implementations with temp directories
- API tests use `app.dependency_overrides` for DI substitution

## Configuration

All settings use the `IMG_` environment variable prefix via pydantic-settings. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `IMG_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/images` | DB connection |
| `IMG_STORAGE_BASE_DIR` | `/data/images` | File storage path |
| `IMG_PROCESSING_MAX_WORKERS` | `4` | CPU worker pool size |
| `IMG_THUMBNAIL_MAX_SIZE` | `256` | Max thumbnail dimension (px) |
| `IMG_RETENTION_BATCH_SIZE` | `100` | Expired images per sweep |

## Boundaries

- ✅ **Always do**: Run `ruff check` and `pytest` before committing. Follow the 4-layer dependency rule. Use abstract ports in domain/application layers. Write type hints for all function signatures.
- ⚠️ **Ask first**: Database schema changes (`models.py`), adding new dependencies to `requirements.txt`, modifying Dockerfile or k8s manifests, changing the DI wiring in `dependencies.py`.
- 🚫 **Never do**: Import infrastructure/presentation code in the domain layer. Commit database credentials or secrets. Modify `__pycache__/` or `.egg-info/` directories. Remove failing tests without authorization. Use synchronous database calls — all DB access must be async.

## Progressive Disclosure

This AGENTS.md is intentionally kept focused. For detailed reference:

- **Ruff/mypy config**: See `pyproject.toml` for full linting rules, line-length, and type-checking settings.
- **Database schema**: See `src/infrastructure/database/models.py` for ORM models and indexes.
- **DI wiring**: See `src/presentation/api/dependencies.py` for how use cases are assembled.
- **Test fixtures**: See `tests/conftest.py` for all shared fixtures and mock factories.
- **Docker/K8s**: See `docker-compose.yml`, `k8s/`, and `minikube/` for deployment manifests.
- **API endpoints**: See `src/presentation/api/routes/` or run the dev server and visit `/docs`.
- **C++ extension**: See `cpp/` for the optional pybind11-based fast resize module.

Avoid adding reactive rules here. If a rule only applies to one domain (e.g., testing patterns, API design), put it in a doc close to that code instead of growing this file.
