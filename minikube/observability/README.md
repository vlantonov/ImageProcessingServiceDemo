# Observability Stack — Minikube

Deploys Prometheus, Tempo, Loki, Promtail, and Grafana into a separate
`observability` namespace alongside the image-processing-service.

## Architecture

```
cv-platform namespace                    observability namespace
┌─────────────────────┐                  ┌───────────────────────────┐
│  image-service      │──── metrics ───→ │  Prometheus (:9090)       │
│  (:8000 /metrics)   │                  │                           │
│                     │──── traces ────→ │  Tempo (:4317 OTLP gRPC)  │
│                     │                  │                           │
│  (stdout JSON logs) │──── logs ──────→ │  Promtail → Loki (:3100)  │
└─────────────────────┘                  │                           │
                                         │  Grafana (:3000)          │
                                         │   ├─ RED Metrics dashboard│
                                         │   ├─ Traces dashboard     │
                                         │   └─ Logs dashboard       │
                                         └───────────────────────────┘
```

## Quick Start

```bash
# 1. Deploy the app first
./minikube/setup.sh

# 2. Deploy observability stack
./minikube/observability/setup.sh

# 3. Open Grafana
minikube service grafana --namespace=observability

# 4. Clean up
./minikube/observability/teardown.sh
```

## Grafana Dashboards

| Dashboard | UID | Description |
|-----------|-----|-------------|
| **RED Metrics** | `image-service-red` | Request rate, error rate, latency percentiles, saturation |
| **Traces** | `image-service-traces` | Service map, recent traces, duration distribution |
| **Logs** | `image-service-logs` | Application logs, log volume by level, error logs |

Default credentials: `admin` / `admin`

## Components

| Component | Image | Port | Purpose |
|-----------|-------|------|---------|
| Prometheus | `prom/prometheus:v2.53.0` | 9090 | Metrics scraping and storage |
| Tempo | `grafana/tempo:2.4.1` | 3200 (HTTP), 4317 (OTLP gRPC) | Distributed trace storage |
| Loki | `grafana/loki:2.9.4` | 3100 | Log aggregation |
| Promtail | `grafana/promtail:2.9.4` | 9080 | Log collection (DaemonSet) |
| Grafana | `grafana/grafana:10.4.0` | 3000 (NodePort 30300) | Visualization |

## Configuration

The image-service is configured via the ConfigMap with:

| Variable | Value | Purpose |
|----------|-------|---------|
| `IMG_OTEL_ENABLED` | `true` | Enable OpenTelemetry instrumentation |
| `IMG_OTEL_EXPORTER_OTLP_ENDPOINT` | `http://tempo.observability.svc.cluster.local:4317` | Tempo OTLP endpoint |
| `IMG_OTEL_SERVICE_NAME` | `image-processing-service` | Service name in traces |

## Metrics (RED + Saturation)

- **Rate**: `http_requests_total` — total HTTP requests by method, path, status
- **Errors**: `http_request_errors_total` — 4xx/5xx errors by status code
- **Duration**: `http_request_duration_seconds` — request latency histogram
- **Saturation**: `http_active_requests` — in-flight request count
- **Image processing**: `image_processing_duration_seconds`, `image_uploads_total`

## Traces

OpenTelemetry auto-instruments FastAPI routes and SQLAlchemy queries. Trace IDs
are injected into structured JSON logs for correlation in Grafana (click from
log → trace, or trace → logs).

## Logs

The app emits structured JSON logs (when `IMG_OTEL_ENABLED=true`) with fields:
`timestamp`, `level`, `logger`, `message`, `correlation_id`, `trace_id`, `span_id`.

Promtail collects pod stdout, parses JSON, and ships to Loki. Grafana's Loki
datasource is configured with derived fields to link `trace_id` → Tempo.
