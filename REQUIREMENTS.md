# Image Processing Service — Requirements Specification

---

## 1. Functional Requirements

### FR-1: Image Upload
- **FR-1.1** The system shall accept image uploads via REST API in JPEG, PNG, WebP, and TIFF formats.
- **FR-1.2** The system shall reject uploads exceeding 50 MB with HTTP 413.
- **FR-1.3** The system shall reject unsupported content types with HTTP 415.
- **FR-1.4** The system shall persist image binary data to a storage backend and metadata to a database.
- **FR-1.5** The system shall allow users to attach tags (string labels) to uploaded images.
- **FR-1.6** The system shall allow users to specify a TTL (time-to-live) in hours for automatic expiry.

### FR-2: Image Processing
- **FR-2.1** The system shall generate a thumbnail (max 256×256 px) from an uploaded image.
- **FR-2.2** The system shall extract metadata (width, height, format, size, channels) during processing.
- **FR-2.3** The system shall track processing status per image: `pending` → `processing` → `completed` | `failed`.
- **FR-2.4** The system shall support single-image processing via a dedicated endpoint.
- **FR-2.5** The system shall support batch processing of multiple images in a single request with configurable concurrency.

### FR-3: Image Retrieval
- **FR-3.1** The system shall allow retrieval of image metadata by ID.
- **FR-3.2** The system shall allow download of the original image file by ID.
- **FR-3.3** The system shall allow download of the thumbnail by ID (when available).
- **FR-3.4** The system shall provide a paginated listing endpoint with offset/limit parameters.
- **FR-3.5** The system shall support filtering images by processing status.

### FR-4: Retention & Lifecycle
- **FR-4.1** The system shall automatically mark images as expired when their TTL elapses.
- **FR-4.2** The system shall provide a retention sweep endpoint that deletes expired images (metadata + files).
- **FR-4.3** The system shall process expired images in configurable batch sizes to avoid overloading the database.

### FR-5: Health & Observability
- **FR-5.1** The system shall expose a `/health` endpoint returning service name, version, and status.
- **FR-5.2** The system shall log every incoming request with method, path, status code, and latency.

### FR-6: API Documentation
- **FR-6.1** The system shall auto-generate interactive API documentation (Swagger UI at `/docs`).
- **FR-6.2** The system shall auto-generate ReDoc documentation at `/redoc`.

---

## 2. Non-Functional Requirements

### NFR-1: Architecture & Code Quality
- **NFR-1.1** The system shall follow **Clean Architecture** with strict layer separation: Domain → Application → Infrastructure → Presentation.
- **NFR-1.2** The domain layer shall have **zero external dependencies** (no framework, no ORM imports).
- **NFR-1.3** Infrastructure implementations shall depend on domain interfaces (Dependency Inversion Principle).
- **NFR-1.4** The codebase shall adhere to **Clean Code** principles: single responsibility, meaningful names, small focused functions, no god objects.
- **NFR-1.5** The system shall be structured as an independently deployable **microservice** with well-defined API boundaries.

### NFR-2: Performance & Scalability
- **NFR-2.1** CPU-bound image processing shall be offloaded to a `ProcessPoolExecutor` to keep the async event loop responsive.
- **NFR-2.2** Batch processing shall use `asyncio.gather` with a `Semaphore` for bounded concurrency control.
- **NFR-2.3** Database connections shall use **async connection pooling** with configurable pool size and overflow.
- **NFR-2.4** Database queries shall use **indexes** on frequently filtered columns (status, created_at, expires_at).
- **NFR-2.5** Listing endpoints shall use **pagination** (offset + limit) to avoid full table scans.
- **NFR-2.6** File I/O shall be non-blocking (delegated to thread pool via `asyncio.to_thread`).

### NFR-3: Containerization & Orchestration
- **NFR-3.1** The application shall be packaged via a **multi-stage Docker build** to minimize image size.
- **NFR-3.2** The container shall run as a **non-root user** for security.
- **NFR-3.3** The system shall be deployable on **Kubernetes** with Deployment, Service, ConfigMap, PVC, and HPA manifests.
- **NFR-3.4** Kubernetes deployments shall include **liveness and readiness probes** on the health endpoint.
- **NFR-3.5** The system shall support **horizontal autoscaling** based on CPU/memory utilization via HPA.
- **NFR-3.6** A complete **minikube demo** shall be provided for local Kubernetes validation.

### NFR-4: Configuration & Portability
- **NFR-4.1** All configuration shall be provided via **environment variables** (12-factor app, `IMG_` prefix).
- **NFR-4.2** Configuration shall be validated at startup using **pydantic-settings** with type-safe defaults.
- **NFR-4.3** The storage backend shall be abstracted behind a domain interface, allowing swap from local filesystem to S3/GCS without application changes.

### NFR-5: Security
- **NFR-5.1** Input files shall be validated for content type before processing.
- **NFR-5.2** Upload size shall be bounded to prevent resource exhaustion.
- **NFR-5.3** The Docker container shall run as a non-privileged user.
- **NFR-5.4** Database credentials shall be injectable via environment variables (not hardcoded in production).

### NFR-6: Testability
- **NFR-6.1** Domain entities shall be testable in isolation with no infrastructure dependencies (pure unit tests).
- **NFR-6.2** Application use cases shall be testable with mocked ports (repository, storage, processor).
- **NFR-6.3** Infrastructure components shall have integration tests with real I/O (filesystem, Pillow).
- **NFR-6.4** API endpoints shall have integration tests using FastAPI `TestClient` with dependency overrides.
- **NFR-6.5** The test suite shall pass without any external services (no running database required).

### NFR-7: C++ Performance Module (Nice-to-Have)
- **NFR-7.1** A C++ module shall provide optimized bilinear interpolation resize for 8-bit RGB/RGBA images.
- **NFR-7.2** The C++ module shall be callable from Python via **pybind11** bindings.
- **NFR-7.3** The C++ module shall build with **CMake** and provide a build script.

---

## 3. Traceability Matrix

| Req ID | Requirement | Implementation |
|--------|-------------|----------------|
| FR-1.1 | Image upload (JPEG/PNG/WebP/TIFF) | `routes/images.py` — `ALLOWED_CONTENT_TYPES` set, `upload_image` endpoint |
| FR-1.2 | 50 MB size limit | `routes/images.py` — `MAX_UPLOAD_SIZE` check |
| FR-1.3 | Reject unsupported types | `routes/images.py` — content-type validation → HTTP 415 |
| FR-1.4 | Persist binary + metadata | `UploadImageUseCase` → `ImageStorage.store()` + `ImageRepository.save()` |
| FR-1.5 | Tags on upload | `tags` query param → `Image.tags` field |
| FR-1.6 | TTL-based expiry | `ttl_hours` query param → `Image.expires_at` computed on upload |
| FR-2.1 | Thumbnail generation | `PillowImageProcessor.generate_thumbnail()` via `ProcessPoolExecutor` |
| FR-2.2 | Metadata extraction | `ProcessImageUseCase` → extracts `ImageMetadata` dataclass |
| FR-2.3 | Status lifecycle | `Image.mark_processing()`, `mark_completed()`, `mark_failed()` |
| FR-2.4 | Single image processing | `POST /api/v1/images/{id}/process` |
| FR-2.5 | Batch processing | `POST /api/v1/images/batch/process` → `pipeline.process_batch()` |
| FR-3.1 | Get metadata by ID | `GET /api/v1/images/{id}` |
| FR-3.2 | Download original | `GET /api/v1/images/{id}/download` |
| FR-3.3 | Download thumbnail | `GET /api/v1/images/{id}/download?thumbnail=true` |
| FR-3.4 | Paginated listing | `GET /api/v1/images/?offset=0&limit=50` |
| FR-3.5 | Filter by status | `GET /api/v1/images/?status=completed` |
| FR-4.1 | TTL expiry | `Image.is_expired()`, `ImageRepository.get_expired()` |
| FR-4.2 | Retention sweep | `POST /api/v1/retention/sweep` → `ApplyRetentionUseCase` |
| FR-4.3 | Configurable batch size | `IMG_RETENTION_BATCH_SIZE` env var |
| FR-5.1 | Health endpoint | `GET /health` → `HealthResponse` |
| FR-5.2 | Request logging | `RequestLoggingMiddleware` logs method, path, status, latency |
| FR-6.1 | Swagger UI | FastAPI `docs_url="/docs"` |
| FR-6.2 | ReDoc | FastAPI `redoc_url="/redoc"` |
| NFR-1.1 | Clean Architecture layers | `src/domain/`, `src/application/`, `src/infrastructure/`, `src/presentation/` |
| NFR-1.2 | Domain zero-deps | `domain/` imports only stdlib + own entities |
| NFR-1.3 | Dependency Inversion | `domain/interfaces/` ports implemented by `infrastructure/` adapters |
| NFR-1.4 | Clean Code | SRP classes, small functions, type hints, meaningful names |
| NFR-1.5 | Microservice design | Self-contained with REST API, independent deployment |
| NFR-2.1 | ProcessPoolExecutor | `pillow_processor.py` — `loop.run_in_executor()` |
| NFR-2.2 | Bounded concurrency | `pipeline.py` — `asyncio.Semaphore` + `asyncio.gather` |
| NFR-2.3 | Async connection pooling | `session.py` — `pool_size`, `max_overflow`, `pool_pre_ping` |
| NFR-2.4 | Database indexes | `models.py` — indexes on `status`, `created_at`, `expires_at` |
| NFR-2.5 | Pagination | `ImageRepository.list_images(offset, limit)` |
| NFR-2.6 | Non-blocking file I/O | `local_image_storage.py` — `asyncio.to_thread()` |
| NFR-3.1 | Multi-stage Docker | `Dockerfile` — builder + runtime stages |
| NFR-3.2 | Non-root container | `Dockerfile` — `appuser` user |
| NFR-3.3 | K8s manifests | `k8s/` and `minikube/` directories |
| NFR-3.4 | Liveness/readiness probes | `deployment.yaml` — `httpGet /health` |
| NFR-3.5 | HPA autoscaling | `hpa.yaml` — CPU/memory targets |
| NFR-3.6 | Minikube demo | `minikube/setup.sh`, `demo.sh`, `teardown.sh` |
| NFR-4.1 | Env var config | `pydantic-settings` with `IMG_` prefix |
| NFR-4.2 | Type-safe config | `Settings` class with typed defaults |
| NFR-4.3 | Storage abstraction | `ImageStorage` interface → `LocalImageStorage` adapter |
| NFR-5.1 | Content-type validation | `ALLOWED_CONTENT_TYPES` check before processing |
| NFR-5.2 | Upload size bound | `MAX_UPLOAD_SIZE = 50 MB` |
| NFR-5.3 | Non-root Docker | `USER appuser` in Dockerfile |
| NFR-5.4 | Injectable credentials | `IMG_DATABASE_URL` env var |
| NFR-6.1 | Pure domain unit tests | `tests/domain/` — no mocks, no I/O |
| NFR-6.2 | Mocked use case tests | `tests/application/` — `AsyncMock` for all ports |
| NFR-6.3 | Infrastructure integration tests | `tests/infrastructure/` — real Pillow + filesystem |
| NFR-6.4 | API integration tests | `tests/presentation/` — `TestClient` + dependency overrides |
| NFR-6.5 | No external services | All 29 tests pass without a running database |
| NFR-7.1 | C++ bilinear resize | `cpp/fast_resize.cpp` — `bilinear_resize()` function |
| NFR-7.2 | pybind11 bindings | `PYBIND11_MODULE(fast_resize, m)` in `fast_resize.cpp` |
| NFR-7.3 | CMake build | `cpp/CMakeLists.txt` + `cpp/build.sh` |
