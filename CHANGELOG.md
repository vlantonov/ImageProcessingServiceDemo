# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[unreleased]: https://github.com/vlantonov/ImageProcessingServiceDemo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/vlantonov/ImageProcessingServiceDemo/releases/tag/v1.0.0
