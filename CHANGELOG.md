# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[unreleased]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/vlantonov/ImageProcessingServiceDemo/releases/tag/v1.0.0
