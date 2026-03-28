# Image Processing Service — Project Description

## Overview

This project is a **high-performance, microservices-ready image processing backend** that demonstrates the core competencies required for the **Senior Software Engineer (Architecture & Data Processing)** role on a Computer Vision Team. The service accepts image uploads, generates thumbnails, extracts metadata, applies configurable retention policies, and serves files — all through a fast, well-documented REST API. It is designed to handle gigantic amounts of image data efficiently, using parallelization, asynchronous processing, and scalable infrastructure.

---

## Software Architecture & Development

The system is built according to strict **Clean Architecture** principles with four clearly separated layers and enforced **Dependency Inversion**:

```
┌─────────────────────────────────────────────────────────────────┐
│  Presentation Layer  (FastAPI routes, Pydantic schemas,         │
│                       middleware, dependency injection)         │
├─────────────────────────────────────────────────────────────────┤
│  Application Layer   (use cases, DTOs — orchestration logic)    │
├─────────────────────────────────────────────────────────────────┤
│  Domain Layer        (entities, interfaces/ports — zero deps)   │
├─────────────────────────────────────────────────────────────────┤
│  Infrastructure      (PostgreSQL adapter, Pillow processor,     │
│                       local file storage, async DB session)     │
└─────────────────────────────────────────────────────────────────┘
```

- **Domain Layer** defines pure business entities (`Image`, `RetentionPolicy`) and abstract ports (`ImageProcessor`, `ImageRepository`, `ImageStorage`) with zero external dependencies.
- **Application Layer** contains use cases (`UploadImage`, `ProcessImage`, `GetImage`, `ListImages`, `ApplyRetention`) that orchestrate domain logic through ports, using frozen dataclass DTOs for data transfer.
- **Infrastructure Layer** provides concrete adapters: PostgreSQL repository via async SQLAlchemy, Pillow-based image processor with `ProcessPoolExecutor` parallelism, and a local file storage backend.
- **Presentation Layer** exposes FastAPI routes with Pydantic validation, request logging middleware, and a dedicated dependency injection module that wires infrastructure into use cases.

Each layer depends only inward — infrastructure and presentation never leak into the domain. This ensures testability, maintainability, and the ability to swap out adapters (e.g., replacing local storage with S3) without modifying business logic.

**Clean Code** is applied throughout: single-responsibility classes, descriptive naming, small focused functions, and no god objects.

---

## Efficient Image Processing

The service implements **high-performance pipelines** for processing large amounts of image data:

- **CPU-bound parallelism**: Thumbnail generation and metadata extraction are offloaded to a `ProcessPoolExecutor`, keeping the async event loop fully responsive under heavy load. Pure synchronous Pillow functions run in worker processes while the main thread continues handling requests.
- **Bounded batch concurrency**: A batch processing pipeline uses `asyncio.Semaphore` combined with `asyncio.gather` to process multiple images concurrently with a configurable concurrency limit (1–32), preventing resource exhaustion while maximizing throughput.
- **Non-blocking file I/O**: All storage operations (`store`, `retrieve`, `delete`) use `asyncio.to_thread()` so that disk reads/writes never block the event loop.
- **Content-addressed storage**: Uploaded files are stored with a SHA256-based filename prefix, enabling deduplication and safe concurrent writes.

Supported image formats: JPEG, PNG, WebP, TIFF — with a configurable maximum upload size (default 50 MB).

---

## Databases & Retention

### Database Design & Scaling

- **Async PostgreSQL** access via `asyncpg` + SQLAlchemy 2.0 async engine, providing true non-blocking database I/O.
- **Connection pooling** with configurable `pool_size` and `max_overflow` parameters, along with `pool_pre_ping` for automatic stale connection recovery.
- **Strategic indexing**: Indexes on `status`, `created_at`, and a **partial index** on `expires_at` (only for non-null values) to keep retention queries fast without bloating write-heavy paths.
- **Paginated queries** via offset/limit with total count, avoiding full table scans on large datasets.
- **Entity ↔ ORM mapping**: Clean separation between domain entities and SQLAlchemy models, ensuring the domain stays persistence-agnostic.

### Retention Strategies

- Images can be uploaded with an optional **TTL** (1–8,760 hours). Expiry time is computed at upload and stored as `expires_at`.
- The `ApplyRetentionUseCase` performs batch sweeps: it fetches expired images in configurable batches, deletes both original files and thumbnails from storage, removes metadata from the database, and logs successes and failures.
- Retention sweeps are triggered via a dedicated REST endpoint (`POST /api/v1/retention/sweep`), suitable for integration with external schedulers (cron, Kubernetes CronJobs).
- Domain-level `RetentionPolicy` entities support tag-based matching for flexible, policy-driven cleanup.

---

## REST API Design (FastAPI)

Fast, reliable REST APIs are designed and developed with **FastAPI**:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness/readiness probe for Kubernetes |
| `POST` | `/api/v1/images/` | Upload an image with optional tags and TTL |
| `GET` | `/api/v1/images/` | List images with pagination and status filter |
| `GET` | `/api/v1/images/{id}` | Retrieve image metadata |
| `GET` | `/api/v1/images/{id}/download` | Download original image or thumbnail |
| `POST` | `/api/v1/images/{id}/process` | Process a single image (thumbnail + metadata) |
| `POST` | `/api/v1/images/batch/process` | Process multiple images concurrently |
| `POST` | `/api/v1/retention/sweep` | Trigger retention cleanup |

**API quality features:**
- Pydantic schemas with strict validation (max 20 tags, TTL range enforcement, max upload size)
- Proper HTTP status codes (201 Created, 404 Not Found, 413 Payload Too Large, 415 Unsupported Media Type)
- Content-type enforcement for upload security
- Automatic OpenAPI/Swagger documentation at `/docs` and ReDoc at `/redoc`
- Request logging middleware tracking method, path, status, and response time

---

## Infrastructure: Docker & Kubernetes

### Docker

- **Multi-stage Dockerfile**: A builder stage installs Python dependencies, and a minimal runtime stage copies only the installed packages and application code — reducing image size and attack surface.
- **Security**: The container runs as a non-root user (`appuser`), following container security best practices.
- **Docker Compose**: Orchestrates the application service and PostgreSQL database with health-check–based startup ordering and named volumes for persistent data.

### Kubernetes

The service is designed to run in a Kubernetes environment with production-grade manifests:

| Manifest | Purpose |
|----------|---------|
| `deployment.yaml` | 2 replicas, resource requests/limits, liveness and readiness probes |
| `service.yaml` | ClusterIP service exposing port 80 → 8000 |
| `hpa.yaml` | Horizontal Pod Autoscaler: 2–10 replicas based on CPU (70%) and memory (80%) |
| `configmap.yaml` | Environment configuration (database URL, pool sizes, storage path) |
| `pvc.yaml` | 50Gi PersistentVolumeClaim with ReadWriteMany access |

A complete **Minikube demo** is included (`minikube/`) with automated setup, teardown, and demo scripts that deploy the full stack locally and exercise all API endpoints.

---

## 12-Factor Configuration

All settings are provided via environment variables (prefix `IMG_`) using **pydantic-settings**, ensuring type-safe, validated configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `IMG_DATABASE_URL` | `postgresql+asyncpg://...` | Async database connection string |
| `IMG_DB_POOL_SIZE` | `10` | Connection pool size |
| `IMG_DB_MAX_OVERFLOW` | `20` | Maximum overflow connections |
| `IMG_STORAGE_BASE_DIR` | `/data/images` | File storage path |
| `IMG_PROCESSING_MAX_WORKERS` | `4` | ProcessPoolExecutor worker count |
| `IMG_THUMBNAIL_MAX_SIZE` | `256` | Thumbnail max dimension (pixels) |
| `IMG_RETENTION_BATCH_SIZE` | `100` | Expired images per retention sweep |
| `IMG_DEBUG` | `false` | Enable debug logging |

---

## C++ Performance Module (Nice-to-Have)

For particularly performance-critical image processing scenarios, the project includes an **optional C++ module** compiled with pybind11:

- **`fast_resize.cpp`**: Implements bilinear interpolation for 8-bit RGB/RGBA image resizing, achieving 10–100× speedup over pure-Python Pillow for large batch operations.
- Built with CMake (C++17, `-O3` optimization) and directly callable from Python as `fast_resize.bilinear_resize()`.
- The module is optional — the service runs fully functional without it, using Pillow as the default processor.

---

## Testing Strategy

The project includes **29 tests** covering all architectural layers, all passing without requiring external services:

| Layer | Tests | Strategy |
|-------|-------|----------|
| **Domain** | Entity state transitions, expiry logic, retention policy matching | Pure unit tests — no mocks, no I/O |
| **Application** | Use case orchestration (upload, process, retention) | Mocked ports (repository, storage, processor) |
| **Infrastructure** | Pillow thumbnail generation, local file read/write/delete | Real I/O against real Pillow and filesystem (`tmp_path`) |
| **Presentation** | HTTP endpoints, status codes, validation, error handling | FastAPI `TestClient` with dependency overrides |

Test tooling: pytest, pytest-asyncio (auto mode), httpx, aiosqlite (in-memory SQLite for test isolation), ruff (linting), mypy (type checking).

---

## Key Architectural Patterns

| Pattern | Implementation |
|---------|----------------|
| Clean Architecture | 4-layer separation with inward-only dependencies |
| Dependency Inversion | Domain defines abstract ports; infrastructure provides adapters |
| SOLID Principles | Single responsibility, interface segregation, open/closed |
| Async/Await | Entire codebase is asynchronous — non-blocking I/O throughout |
| ProcessPoolExecutor | CPU-bound image work dispatched to worker processes |
| Bounded Concurrency | `asyncio.Semaphore` + `asyncio.gather` for batch processing |
| Connection Pooling | Async SQLAlchemy pool with configurable size and overflow |
| Partial Indexes | Database index on `expires_at` for non-null values only |
| Multi-Stage Docker | Builder/runtime separation for minimal production images |
| Horizontal Autoscaling | Kubernetes HPA scales pods based on CPU and memory metrics |
| 12-Factor Config | Type-safe environment variables via pydantic-settings |
| FastAPI DI | Routes depend on use case abstractions, not concrete implementations |

---

## Technology Stack

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.11+ (primary), C++17 (optional module) |
| **Web Framework** | FastAPI, Uvicorn (ASGI) |
| **Database** | PostgreSQL 16, SQLAlchemy 2.0 (async), asyncpg |
| **Image Processing** | Pillow, pybind11 (C++ bridge) |
| **Validation** | Pydantic v2, pydantic-settings |
| **Containerization** | Docker (multi-stage), Docker Compose |
| **Orchestration** | Kubernetes, Minikube (local demo) |
| **Testing** | pytest, pytest-asyncio, httpx, aiosqlite |
| **Code Quality** | ruff (linter/formatter), mypy (type checker) |
| **Migrations** | Alembic |
