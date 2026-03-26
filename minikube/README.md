# Minikube Demo

Run the complete image-processing-service on a local Kubernetes cluster.

## Prerequisites

- [minikube](https://minikube.sigs.k8s.io/docs/start/) installed
- [kubectl](https://kubernetes.io/docs/tasks/tools/) installed
- [Docker](https://docs.docker.com/get-docker/) installed
- `curl` and `jq` (for the demo script)
- Python 3.11+ with Pillow (for generating test images in the demo)

## Quick Start

```bash
# 1. Deploy everything (starts minikube if needed)
./minikube/setup.sh

# 2. Run the interactive API demo
./minikube/demo.sh

# 3. Clean up when done
./minikube/teardown.sh        # delete namespace
./minikube/teardown.sh --all  # also stop minikube
```

## What `setup.sh` Does

1. Starts minikube (if not already running) with 2 CPUs and 4 GB RAM
2. Configures the shell to use minikube's Docker daemon
3. Builds the `image-service:latest` Docker image inside minikube
4. Enables the metrics-server addon (for HPA)
5. Applies all Kubernetes manifests in order:
   - Namespace (`cv-platform`)
   - ConfigMap (env vars)
   - PostgreSQL (Deployment + Service + PVC)
   - Image data PVC
   - Image service Deployment
   - NodePort Service (port 30080)
   - HorizontalPodAutoscaler
6. Waits for all pods to be ready
7. Prints the service URL

## What `demo.sh` Exercises

| Step | API Endpoint | What It Shows |
|------|-------------|---------------|
| 1 | `GET /health` | K8s liveness/readiness probe |
| 2 | — | Generates test PNG images locally |
| 3 | `POST /api/v1/images/` | Upload with tags |
| 4 | `POST /api/v1/images/?ttl_hours=1` | Upload with TTL for retention |
| 5 | `GET /api/v1/images/` | Paginated listing |
| 6 | `GET /api/v1/images/{id}` | Single image metadata |
| 7 | `POST /api/v1/images/{id}/process` | Thumbnail generation + metadata extraction |
| 8 | `POST /api/v1/images/batch/process` | Parallel batch processing |
| 9 | `GET /api/v1/images/{id}/download` | Download original + thumbnail |
| 10 | `GET /api/v1/images/?status=completed` | Filter by status |
| 11 | `POST /api/v1/retention/sweep` | Expired image cleanup |
| 12 | `kubectl get pods/svc/hpa` | K8s resource status |

## Kubernetes Resources

```
cv-platform namespace
├── postgres (Deployment, 1 replica)
│   ├── postgres-svc (ClusterIP :5432)
│   └── postgres-pvc (1Gi)
├── image-service (Deployment, 1 replica)
│   ├── image-service (NodePort :80 → :8000, nodePort 30080)
│   ├── image-data-pvc (2Gi)
│   └── image-service-hpa (1–4 replicas, 70% CPU target)
└── image-service-config (ConfigMap)
```

## Manual Access

```bash
# Get the service URL
minikube service image-service --namespace=cv-platform --url

# Open Swagger UI in browser
minikube service image-service --namespace=cv-platform

# View pod logs
kubectl logs -n cv-platform deployment/image-service -f

# Check HPA status
kubectl get hpa -n cv-platform -w

# Scale manually
kubectl scale deployment/image-service -n cv-platform --replicas=3
```
