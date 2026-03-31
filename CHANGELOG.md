# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Moved database credentials out of source code and configuration defaults.
  `IMG_DB_USER` and `IMG_DB_PASSWORD` are now required environment variables
  with no hardcoded fallback. The `IMG_DATABASE_URL` setting is replaced by
  individual `IMG_DB_USER`, `IMG_DB_PASSWORD`, `IMG_DB_HOST`, `IMG_DB_PORT`,
  and `IMG_DB_NAME` variables. Kubernetes manifests use `Secret` resources
  instead of storing credentials in ConfigMaps. Docker Compose reads
  credentials from the host environment (see `.env.example`).

### Changed

- `Settings.database_url` is now a computed property assembled from individual
  DB credential fields, with password URL-encoding via `urllib.parse.quote_plus`.

## [1.3.0] - 2026-03-31

### Added

- Structured logging with correlation IDs for distributed tracing. Every request
  is assigned a unique correlation ID (or accepts one via `X-Correlation-ID` header),
  which is propagated through all log records and returned in the response header.
- `CorrelationIdFilter` logging filter that injects `correlation_id` into every log record.
- `JSONFormatter` for machine-readable JSON log output (opt-in via `configure_logging(json_output=True)`).
- `configure_logging()` helper replacing `logging.basicConfig()` with correlation-aware formatting.
- Targeted logging across all layers: upload/rejection/404 in routes, image
  lifecycle in use cases, batch start/complete in pipeline, file I/O in storage
  (DEBUG), and cache hit/miss in repository (DEBUG).

### Fixed

- Replaced bare `except Exception:` with `except Exception as e:` in
  `ProcessImageUseCase` to ensure the exception is captured in log output.

## [1.2.4] - 2026-03-31

### Security

- Added per-IP sliding-window rate limiting to upload, processing, and retention
  sweep endpoints to mitigate DoS attacks. Configurable via `IMG_RATE_LIMIT_UPLOAD_MAX`,
  `IMG_RATE_LIMIT_UPLOAD_WINDOW`, `IMG_RATE_LIMIT_PROCESS_MAX`,
  `IMG_RATE_LIMIT_PROCESS_WINDOW`, `IMG_RATE_LIMIT_READ_MAX`, and
  `IMG_RATE_LIMIT_READ_WINDOW` environment variables. Read endpoints (list,
  get, download) use a separate higher limit (60 req/min by default). Returns
  HTTP 429 when the limit is exceeded.

## [1.2.3] - 2026-03-30

### Security

- Added API key authentication for all image and retention endpoints. Set the
  `IMG_API_KEY` environment variable to enforce authentication via the
  `X-API-Key` header. Health endpoints remain open for Kubernetes probes.
  Uses `secrets.compare_digest` for timing-safe key comparison.

## [1.2.2] - 2026-03-30

### Security

- Added image validation on upload: uploaded bytes are verified with Pillow's
  `verify()` and `load()` to reject corrupt, truncated, or malicious files
  before they reach storage or processing. Decompression bombs are blocked via
  a 100-megapixel limit, and only JPEG/PNG/WEBP/TIFF formats are accepted.
- Explicitly set `ImageFile.LOAD_TRUNCATED_IMAGES = False` in the Pillow
  processor to prevent partial parsing of corrupt images that could trigger
  Pillow CVEs.
- Added filename sanitization on upload to prevent path-traversal attacks
  (`../../../etc/passwd`), null-byte injection, and hidden-file creation.
  `LocalImageStorage.store()` also validates the resolved path stays inside
  the base directory as defence-in-depth.

## [1.2.1] - 2026-03-29

### Fixed

- `ProcessPoolExecutor` in `PillowImageProcessor` is now shut down during app
  lifespan teardown, preventing leaked worker processes on exit.
- Race condition in retention sweeps: concurrent calls to `get_expired()` could
  fetch the same rows, causing double-delete attempts on storage files. Added
  `delete_expired_batch()` which uses `SELECT … FOR UPDATE SKIP LOCKED` to
  atomically claim and delete expired rows in a single transaction.
- `ProcessImageUseCase` now cleans up the stored thumbnail if the final
  metadata save fails, preventing orphaned files and an image stuck in
  `PROCESSING` state.
- Narrowed overly broad `except Exception` handlers: `apply_retention.py` and
  `process_image.py` now catch `OSError` for storage operations;
  `pipeline.py` uses `asyncio.gather(return_exceptions=True)` instead of
  swallowing exceptions inside coroutines.

## [1.2.0] - 2026-03-29

### Added

- In-memory TTL cache for image metadata lookups (`get_by_id`), avoiding redundant
  database hits on repeated reads. Implemented as a `CachedImageRepository` decorator
  wrapping the existing `PostgresImageRepository`.
- New `IMG_CACHE_TTL_SECONDS` (default 60) and `IMG_CACHE_MAX_SIZE` (default 1024)
  configuration settings for cache tuning.

### Changed

- Health endpoint (`/health`) now reads version from `importlib.metadata` instead of
  hardcoding `"1.0.0"`, and verifies database connectivity (`SELECT 1`) and storage
  directory existence. Response includes a `checks` map with per-component status;
  overall status reports `"degraded"` if any check fails.
- `list_images()` and `get_expired()` now use server-side cursors
  (`session.stream_scalars`) instead of buffered `execute` + `all()`, reducing peak
  memory usage for large result sets.
- C++ `bilinear_resize` uses SSE2 SIMD intrinsics on x86-64 to interpolate all
  channels per pixel in parallel, with a scalar fallback for other architectures.
  Arithmetic switched from `double` to `float` for better vectorization throughput.
- C++ `bilinear_resize` now accepts and returns NumPy `uint8` arrays
  (`py::array_t<uint8_t>`) instead of `std::vector<uint8_t>`, eliminating the
  per-element copy between Python lists and C++ vectors. CMake builds with
  `-march=native` to enable host-optimal SIMD.

### Fixed

- C++ `fast_resize.cpp` now passes `clang-tidy` with `bugprone-*`, `readability-*`,
  `performance-*`, and `modernize-*` checks: renamed short identifiers, added explicit
  `static_cast`, extracted magic numbers to constants, used uppercase float literal
  suffixes, added parentheses for clarity, and passed NumPy array by `const&`.

## [1.1.0] - 2026-03-28

### Added

- GitLab CI pipeline (`.gitlab-ci.yml`) mirroring the GitHub Actions setup: Python
  lint/test on 3.11 and 3.12, C++ build with GCC/Clang, and clang-tidy lint.
- GitHub Actions CI workflow for Python: ruff lint/format, mypy type checking, and pytest
  with coverage on Python 3.11 and 3.12.
- GitHub Actions CI workflow for C++: build with GCC and Clang, clang-tidy lint
  (triggered on `cpp/` path changes).
- `pytest-cov` added to dev dependencies for coverage reporting.

### Fixed

- Integer overflow in `fast_resize.cpp` `bilinear_resize` buffer size check: cast to
  `size_t` before multiplication instead of after.

## [1.0.2] - 2026-03-28

### Fixed

- Upload route now enforces a maximum of 20 tags per image (FR-1.5, NFR-5.5).
  Previously the `ImageUploadParams` schema had the constraint but the route did not apply it.
- `ProcessImageUseCase` now logs processing failures via `logger.exception()` before marking
  the image as `FAILED` (FR-2.6, FR-5.2), improving observability for debugging.
- Replaced deprecated `HTTP_422_UNPROCESSABLE_ENTITY` with `HTTP_422_UNPROCESSABLE_CONTENT`.

### Added

- `test_upload_too_many_tags` API test covering the 20-tag limit enforcement.

### Changed

- `REQUIREMENTS.md` updated with refined functional and non-functional requirements,
  covering edge cases (tag limits, TTL ranges, batch bounds, error-resilient sweep,
  partial indexes, K8s resource specs, PVC details).

## [1.0.1] - 2026-03-27

### Added

- Changelog section in AGENTS.md with [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) maintenance rules.
- Version bump rule requiring SemVer classification of PR diffs before merge.
- `CHANGELOG.md` update requirement in Boundaries and PR Checklist.
- Changelog reference in Progressive Disclosure section.
- Changelog guidance (item 7) and version bump rule in AGENTS_MD_PROMPT.md prompt template.

### Changed

- PR Checklist now requires inspecting the full diff to determine the correct SemVer bump
  and updating version in `pyproject.toml` and `CHANGELOG.md` before merge.

## [1.0.0] - 2026-03-27

### Added

- Clean Architecture image processing microservice with FastAPI, SQLAlchemy 2.0 (async),
  and PostgreSQL.
- Domain layer with `Image` entity, `ProcessingStatus` enum, `RetentionPolicy`, and abstract
  ports (`ImageRepository`, `ImageStorage`, `ImageProcessor`).
- Application layer with use cases: upload image, process image, get image, list images,
  apply retention policy.
- Infrastructure layer with PostgreSQL repository, Pillow-based image processor, processing
  pipeline, and local filesystem storage adapter.
- Presentation layer with FastAPI routes, Pydantic schemas, middleware, and dependency injection
  wiring.
- Frozen-dataclass DTOs for application layer responses.
- Configuration via pydantic-settings with `IMG_` environment variable prefix.
- Full test suite across all four architecture layers (domain, application, infrastructure,
  presentation) with no external service dependencies.
- Docker and Docker Compose setup for containerized deployment.
- Kubernetes manifests (`k8s/`) and Minikube demo scripts (`minikube/`).
- Optional C++ extension (`cpp/`) with pybind11-based fast image resize module.
- AGENTS.md with coding guidelines, architecture rules, and progressive disclosure references.
- AGENTS_MD_PROMPT.md with prompt templates for generating AGENTS.md files.
- Project documentation: README.md, PROJECT_DESCRIPTION.md, REQUIREMENTS.md.

### Fixed

- Minikube demo script corrections.
- Miscellaneous code fixes and AGENTS.md refinements.
- Use `StrEnum` instead of `(str, Enum)` for `ProcessingStatus` (ruff UP042).
- Use `Annotated[T, Depends(...)]` instead of bare `Depends()` defaults in FastAPI routes (ruff B008).
- Replace mutable default `[]` with `None` for `tags` query parameter (ruff B006/RUF013).
- Fix `type: ignore` comment on `rowcount` to use correct mypy error code `attr-defined`.
- Add proper type annotation for `settings` parameter in retention sweep endpoint.

[unreleased]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.2.3...HEAD
[1.2.3]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.2.2...v1.2.3
[1.2.2]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/vlantonov/ImageProcessingServiceDemo/releases/tag/v1.0.0
