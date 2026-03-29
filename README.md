# Image Processing Service

High-performance, microservices-ready image processing backend built with **Clean Architecture** principles.

* **[Project Description](PROJECT_DESCRIPTION.md)** — Architecture deep-dive, design patterns, and technology stack
* **[Requirements Specification](REQUIREMENTS.md)** — Functional/non-functional requirements with traceability matrix

## Quick Start

### Local Development

```bash
# Create virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Start the server (requires PostgreSQL)
export IMG_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/images"
uvicorn src.main:app --reload
```

### Docker Compose

```bash
docker compose up --build
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### Minikube (Local Kubernetes)

```bash
cd minikube && ./setup.sh    # deploy full stack
./demo.sh                    # exercise all endpoints
./teardown.sh                # clean up
```

See [minikube/README.md](minikube/README.md) for details.

### Kubernetes (Production)

```bash
kubectl create namespace cv-platform
kubectl apply -f k8s/
```

### Build C++ Module (Optional)

```bash
pip install pybind11
cd cpp && ./build.sh
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness/readiness probe |
| `POST` | `/api/v1/images/` | Upload an image (JPEG, PNG, WebP, TIFF) |
| `GET` | `/api/v1/images/` | List images (paginated, filterable by status) |
| `GET` | `/api/v1/images/{id}` | Get image metadata |
| `GET` | `/api/v1/images/{id}/download` | Download original or thumbnail |
| `POST` | `/api/v1/images/{id}/process` | Process a single image |
| `POST` | `/api/v1/images/batch/process` | Process multiple images concurrently |
| `POST` | `/api/v1/retention/sweep` | Trigger retention cleanup |

## Configuration

All settings via environment variables (prefix `IMG_`), validated by [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/):

| Variable | Default | Description |
|----------|---------|-------------|
| `IMG_DATABASE_URL` | `postgresql+asyncpg://...` | Async database connection string |
| `IMG_DB_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `IMG_DB_MAX_OVERFLOW` | `20` | Max overflow connections |
| `IMG_STORAGE_BASE_DIR` | `/data/images` | Image file storage path |
| `IMG_PROCESSING_MAX_WORKERS` | `4` | ProcessPoolExecutor workers |
| `IMG_THUMBNAIL_MAX_SIZE` | `256` | Thumbnail max dimension (px) |
| `IMG_RETENTION_BATCH_SIZE` | `100` | Expired images per sweep |
| `IMG_DEBUG` | `false` | Enable debug logging |

## Project Structure

```
src/
├── config.py                          # 12-factor configuration
├── main.py                            # FastAPI app factory + lifespan
├── domain/                            # Entities & ports (zero external deps)
├── application/                       # Use cases & DTOs
├── infrastructure/                    # Adapters (PostgreSQL, Pillow, filesystem)
└── presentation/                      # FastAPI routes, schemas, middleware

cpp/                                   # Optional C++ resize module (pybind11)
k8s/                                   # Kubernetes manifests (Deployment, HPA, PVC, …)
minikube/                              # Local K8s demo scripts
tests/                                 # tests across all architecture layers
```

## Testing

```bash
pytest tests/ -v
```

All tests pass without external services — domain tests are pure unit tests, application tests use mocked ports, infrastructure tests use real Pillow/filesystem I/O, and API tests use FastAPI `TestClient` with dependency overrides.

