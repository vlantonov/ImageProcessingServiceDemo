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
export IMG_DB_USER="postgres"
export IMG_DB_PASSWORD="postgres"
uvicorn src.main:app --reload
```

### Docker Compose

```bash
docker compose up --build
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

The Docker entrypoint runs `alembic upgrade head` before starting Uvicorn,
so database migrations are applied automatically on every deployment.

### Database Migrations

```bash
# Create a new migration after modifying models.py
alembic revision --autogenerate -m "description of change"

# Apply migrations manually (e.g. local dev)
alembic upgrade head

# Downgrade one revision
alembic downgrade -1
```

### Minikube (Local Kubernetes)

```bash
cd minikube && ./setup.sh    # deploy full stack
./demo.sh                    # exercise all endpoints
./teardown.sh                # clean up
```

See [minikube/README.md](minikube/README.md) for details.

### Observability Stack (Minikube)

```bash
cd minikube/observability && ./setup.sh   # deploy Prometheus, Tempo, Loki, Grafana
minikube service grafana --namespace=observability  # open Grafana
./teardown.sh                             # clean up
```

See [minikube/observability/README.md](minikube/observability/README.md) for dashboards and configuration.

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

All `/api/v1/` endpoints require an `X-API-Key` header when `IMG_API_KEY` is set.
The `/health` endpoint remains open for Kubernetes probes.
Upload, processing, and read endpoints are rate-limited per client IP (HTTP 429 when exceeded).

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
| `IMG_DB_USER` | *(required)* | Database username (no default — must be set) |
| `IMG_DB_PASSWORD` | *(required)* | Database password (no default — must be set) |
| `IMG_DB_HOST` | `localhost` | Database hostname |
| `IMG_DB_PORT` | `5432` | Database port |
| `IMG_DB_NAME` | `images` | Database name |
| `IMG_DB_POOL_SIZE` | `10` | SQLAlchemy connection pool size |
| `IMG_DB_MAX_OVERFLOW` | `20` | Max overflow connections |
| `IMG_STORAGE_BASE_DIR` | `/data/images` | Image file storage path |
| `IMG_PROCESSING_MAX_WORKERS` | `4` | ProcessPoolExecutor workers |
| `IMG_THUMBNAIL_MAX_SIZE` | `256` | Thumbnail max dimension (px) |
| `IMG_RETENTION_BATCH_SIZE` | `100` | Expired images per sweep |
| `IMG_API_KEY` | *(empty)* | API key for `X-API-Key` header auth (empty = disabled) |
| `IMG_RATE_LIMIT_UPLOAD_MAX` | `10` | Max upload requests per window per IP |
| `IMG_RATE_LIMIT_UPLOAD_WINDOW` | `60` | Upload rate limit window (seconds) |
| `IMG_RATE_LIMIT_PROCESS_MAX` | `20` | Max process requests per window per IP |
| `IMG_RATE_LIMIT_PROCESS_WINDOW` | `60` | Process rate limit window (seconds) |
| `IMG_RATE_LIMIT_READ_MAX` | `60` | Max read requests per window per IP |
| `IMG_RATE_LIMIT_READ_WINDOW` | `60` | Read rate limit window (seconds) |
| `IMG_CORS_ORIGINS` | `[]` | Allowed CORS origins (e.g. `["http://localhost:3000"]`; empty = disabled) |
| `IMG_CORS_ALLOW_METHODS` | `["GET","POST","PUT","DELETE","OPTIONS"]` | Allowed HTTP methods for CORS |
| `IMG_CORS_ALLOW_HEADERS` | `["*"]` | Allowed headers for CORS |
| `IMG_DEBUG` | `false` | Enable debug logging |
| `IMG_OTEL_ENABLED` | `false` | Enable OpenTelemetry instrumentation |
| `IMG_OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint for trace export |
| `IMG_OTEL_SERVICE_NAME` | `image-processing-service` | Service name in traces and metrics |

## Project Structure

```
src/
├── config.py                          # 12-factor configuration
├── main.py                            # FastAPI app factory + lifespan
├── domain/                            # Entities & ports (zero external deps)
├── application/                       # Use cases & DTOs
├── infrastructure/                    # Adapters (PostgreSQL, Pillow, filesystem)
│   └── observability/                 # OpenTelemetry setup, metrics, middleware
└── presentation/                      # FastAPI routes, schemas, middleware

migrations/                            # Alembic database migrations
├── env.py                             # Async migration environment
└── versions/                          # Versioned schema change scripts

cpp/                                   # Optional C++ resize module (pybind11)
k8s/                                   # Kubernetes manifests (Deployment, HPA, PVC, …)
minikube/                              # Local K8s demo scripts
│   └── observability/                 # Prometheus, Tempo, Loki, Grafana manifests
tests/                                 # tests across all architecture layers
```

## Testing

```bash
pytest tests/ -v
```

All tests pass without external services — domain tests are pure unit tests, application tests use mocked ports, infrastructure tests use real Pillow/filesystem I/O, and API tests use FastAPI `TestClient` with dependency overrides.

