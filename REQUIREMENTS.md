# Image Processing Service — Requirements Specification

---

## 1. Functional Requirements

### FR-1: Image Upload
- **FR-1.1** The system shall accept image uploads via REST API in JPEG, PNG, WebP, and TIFF formats.
- **FR-1.2** The system shall reject uploads exceeding 50 MB with HTTP 413.
- **FR-1.3** The system shall reject unsupported content types with HTTP 415 (checked before size validation).
- **FR-1.4** The system shall persist image binary data to a storage backend and metadata to a database.
- **FR-1.5** The system shall allow users to attach up to 20 tags (string labels) to uploaded images.
- **FR-1.6** The system shall allow users to specify a TTL (time-to-live) between 1 and 8,760 hours for automatic expiry, computing `expires_at = created_at + ttl_hours`.
- **FR-1.7** The system shall store uploaded images using content-addressed naming (SHA-256 prefix) to enable deduplication of identical files.
- **FR-1.8** The system shall assign newly uploaded images the `PENDING` processing status and return HTTP 201.

### FR-2: Image Processing
- **FR-2.1** The system shall generate a thumbnail (max 256×256 px, aspect ratio preserved) from an uploaded image.
- **FR-2.2** The system shall extract metadata (width, height, format, size, channels) during processing.
- **FR-2.3** The system shall track processing status per image: `PENDING` → `PROCESSING` → `COMPLETED` | `FAILED`.
- **FR-2.4** The system shall support single-image processing via a dedicated endpoint; return HTTP 404 if the image does not exist.
- **FR-2.5** The system shall support batch processing of 1–100 images in a single request with configurable concurrency (1–32, default 8).
- **FR-2.6** On processing failure, the system shall mark the image as `FAILED`, persist the state, and propagate the error.

### FR-3: Image Retrieval
- **FR-3.1** The system shall allow retrieval of image metadata by ID; return HTTP 404 if the image does not exist.
- **FR-3.2** The system shall allow download of the original image file by ID; return HTTP 404 if the image does not exist.
- **FR-3.3** The system shall allow download of the thumbnail by ID via a `thumbnail` query parameter; return `null`/gracefully handle when the thumbnail has not yet been generated.
- **FR-3.4** The system shall provide a paginated listing endpoint with offset/limit (1–100) parameters and return the total count for client-side pagination.
- **FR-3.5** The system shall support filtering images by processing status.
- **FR-3.6** Image metadata responses shall include a derived `thumbnail_available` boolean field.

### FR-4: Retention & Lifecycle
- **FR-4.1** The system shall automatically mark images as expired when their TTL elapses.
- **FR-4.2** The system shall provide a retention sweep endpoint that deletes expired images — including both original and thumbnail files from storage, then the database record.
- **FR-4.3** The system shall process expired images in configurable batch sizes to avoid overloading the database.
- **FR-4.4** The retention sweep response shall include separate `deleted_count` and `errors` counters; individual deletion failures shall not abort the sweep.

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
- **NFR-2.4** Database queries shall use **indexes** on frequently filtered columns (status, created_at, expires_at); the `expires_at` index shall be a **partial index** (`WHERE expires_at IS NOT NULL`) so retention sweeps scan only relevant rows.
- **NFR-2.5** Listing endpoints shall use **pagination** (offset + limit) to avoid full table scans.
- **NFR-2.6** File I/O shall be non-blocking (delegated to thread pool via `asyncio.to_thread`).
- **NFR-2.7** Image files shall be stored with SHA-256 content-addressed naming (12-char hex prefix) to enable deduplication of identical uploads.

### NFR-3: Containerization & Orchestration
- **NFR-3.1** The application shall be packaged via a **multi-stage Docker build** to minimize image size.
- **NFR-3.2** The container shall run as a **non-root user** for security.
- **NFR-3.3** The system shall be deployable on **Kubernetes** with Deployment, Service, ConfigMap, PVC, and HPA manifests.
- **NFR-3.4** Kubernetes deployments shall include **liveness and readiness probes** on the health endpoint.
- **NFR-3.5** The system shall support **horizontal autoscaling** (2–10 replicas) triggered at CPU > 70% or memory > 80% utilization via HPA.
- **NFR-3.6** A complete **minikube demo** shall be provided for local Kubernetes validation.
- **NFR-3.7** Kubernetes deployments shall specify **resource requests** (CPU 250m, memory 512Mi) and **limits** (CPU 1000m, memory 2Gi).
- **NFR-3.8** Persistent storage shall use a **50 Gi ReadWriteMany PVC** to allow shared file access across replicas.

### NFR-4: Configuration & Portability
- **NFR-4.1** All configuration shall be provided via **environment variables** (12-factor app, `IMG_` prefix).
- **NFR-4.2** Configuration shall be validated at startup using **pydantic-settings** with type-safe defaults.
- **NFR-4.3** The storage backend shall be abstracted behind a domain interface, allowing swap from local filesystem to S3/GCS without application changes.

### NFR-5: Security
- **NFR-5.1** Input files shall be validated for content type before processing.
- **NFR-5.2** Upload size shall be bounded to prevent resource exhaustion.
- **NFR-5.3** The Docker container shall run as a non-privileged user.
- **NFR-5.4** Database credentials shall be injectable via environment variables (not hardcoded in production).
- **NFR-5.5** All user-supplied parameters shall be validated at the API boundary: tag count (≤ 20), TTL range (1–8,760 h), batch image IDs (1–100), concurrency (1–32).

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
| FR-1.5 | Tags on upload (max 20) | `ImageUploadParams.tags` — `max_length=20` via Pydantic |
| FR-1.6 | TTL-based expiry (1–8,760 h) | `ImageUploadParams.ttl_hours` — `ge=1, le=8760` via Pydantic |
| FR-1.7 | Content-addressed deduplication | `local_image_storage.py` — SHA-256 12-char hex prefix naming |
| FR-1.8 | Upload returns PENDING + HTTP 201 | `routes/images.py` — `status_code=201` |
| FR-2.1 | Thumbnail generation (aspect preserved) | `PillowImageProcessor.generate_thumbnail()` via `ProcessPoolExecutor` |
| FR-2.2 | Metadata extraction | `ProcessImageUseCase` → extracts `ImageMetadata` dataclass |
| FR-2.3 | Status lifecycle | `Image.mark_processing()`, `mark_completed()`, `mark_failed()` |
| FR-2.4 | Single image processing | `POST /api/v1/images/{id}/process` → HTTP 404 if not found |
| FR-2.5 | Batch processing (1–100 IDs, 1–32 concurrency) | `POST /api/v1/images/batch/process` → `pipeline.process_batch()` |
| FR-2.6 | Failure handling (mark FAILED) | `ProcessImageUseCase` — `image.mark_failed()` + save on exception |
| FR-3.1 | Get metadata by ID | `GET /api/v1/images/{id}` → HTTP 404 if not found |
| FR-3.2 | Download original | `GET /api/v1/images/{id}/download` → HTTP 404 if not found |
| FR-3.3 | Download thumbnail | `GET /api/v1/images/{id}/download?thumbnail=true` → graceful nil |
| FR-3.4 | Paginated listing (limit 1–100) | `GET /api/v1/images/?offset=0&limit=50` + `total` in response |
| FR-3.5 | Filter by status | `GET /api/v1/images/?status=completed` |
| FR-3.6 | `thumbnail_available` field | `ImageOut.thumbnail_available` — derived boolean |
| FR-4.1 | TTL expiry | `Image.is_expired()`, `ImageRepository.get_expired()` |
| FR-4.2 | Retention sweep (both files) | `POST /api/v1/retention/sweep` → deletes original + thumbnail + DB record |
| FR-4.3 | Configurable batch size | `IMG_RETENTION_BATCH_SIZE` env var |
| FR-4.4 | Error-resilient sweep | `ApplyRetentionUseCase` — separate `deleted_count` + `errors` counters |
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
| NFR-2.4 | Database indexes (partial) | `models.py` — partial index `ix_images_expires_at WHERE IS NOT NULL` |
| NFR-2.5 | Pagination | `ImageRepository.list_images(offset, limit)` |
| NFR-2.6 | Non-blocking file I/O | `local_image_storage.py` — `asyncio.to_thread()` |
| NFR-2.7 | Content-addressed dedup | `local_image_storage.py` — SHA-256 12-char hex prefix naming |
| NFR-3.1 | Multi-stage Docker | `Dockerfile` — builder + runtime stages |
| NFR-3.2 | Non-root container | `Dockerfile` — `appuser` user |
| NFR-3.3 | K8s manifests | `k8s/` and `minikube/` directories |
| NFR-3.4 | Liveness/readiness probes | `deployment.yaml` — `httpGet /health` |
| NFR-3.5 | HPA autoscaling (2–10 replicas) | `hpa.yaml` — CPU > 70%, memory > 80% targets |
| NFR-3.6 | Minikube demo | `minikube/setup.sh`, `demo.sh`, `teardown.sh` |
| NFR-3.7 | K8s resource requests/limits | `deployment.yaml` — CPU 250m/1000m, memory 512Mi/2Gi |
| NFR-3.8 | PVC 50Gi ReadWriteMany | `pvc.yaml` — shared storage across replicas |
| NFR-4.1 | Env var config | `pydantic-settings` with `IMG_` prefix |
| NFR-4.2 | Type-safe config | `Settings` class with typed defaults |
| NFR-4.3 | Storage abstraction | `ImageStorage` interface → `LocalImageStorage` adapter |
| NFR-5.1 | Content-type validation | `ALLOWED_CONTENT_TYPES` check before processing |
| NFR-5.2 | Upload size bound | `MAX_UPLOAD_SIZE = 50 MB` |
| NFR-5.3 | Non-root Docker | `USER appuser` in Dockerfile |
| NFR-5.4 | Injectable credentials | `IMG_DATABASE_URL` env var |
| NFR-5.5 | API boundary validation | `ImageUploadParams`, `BatchProcessRequest` — Pydantic constraints |
| NFR-6.1 | Pure domain unit tests | `tests/domain/` — no mocks, no I/O |
| NFR-6.2 | Mocked use case tests | `tests/application/` — `AsyncMock` for all ports |
| NFR-6.3 | Infrastructure integration tests | `tests/infrastructure/` — real Pillow + filesystem |
| NFR-6.4 | API integration tests | `tests/presentation/` — `TestClient` + dependency overrides |
| NFR-6.5 | No external services | All tests pass without a running database |
| NFR-7.1 | C++ bilinear resize | `cpp/fast_resize.cpp` — `bilinear_resize()` function |
| NFR-7.2 | pybind11 bindings | `PYBIND11_MODULE(fast_resize, m)` in `fast_resize.cpp` |
| NFR-7.3 | CMake build | `cpp/CMakeLists.txt` + `cpp/build.sh` |
