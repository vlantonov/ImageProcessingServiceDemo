#!/usr/bin/env bash
# ─── minikube/setup.sh ───────────────────────────────────────────────────────
# Bootstraps the entire image-processing-service in minikube from scratch.
#
# Prerequisites:
#   - minikube installed            (https://minikube.sigs.k8s.io/)
#   - kubectl installed             (https://kubernetes.io/docs/tasks/tools/)
#   - docker installed              (or podman — adjust minikube driver)
#
# Usage:
#   cd <project-root>
#   ./minikube/setup.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

# ── 1. Start minikube if not running ─────────────────────────────────────────
if minikube status --format='{{.Host}}' 2>/dev/null | grep -q Running; then
    ok "Minikube is already running"
else
    info "Starting minikube..."
    minikube start --cpus=2 --memory=4096 --driver=docker
    ok "Minikube started"
fi

# ── 2. Point docker CLI to minikube's daemon ─────────────────────────────────
info "Configuring shell to use minikube's Docker daemon..."
eval "$(minikube -p minikube docker-env)"
ok "Docker context set to minikube"

# ── 3. Build the application image inside minikube ───────────────────────────
info "Building image-service:latest inside minikube..."
docker build -t image-service:latest "$PROJECT_DIR"
ok "Image built: image-service:latest"

# ── 4. Enable metrics-server for HPA (if not already enabled) ────────────────
if minikube addons list 2>/dev/null | grep -q "metrics-server.*enabled"; then
    ok "metrics-server addon already enabled"
else
    info "Enabling metrics-server addon for HPA..."
    minikube addons enable metrics-server
    ok "metrics-server enabled"
fi

# ── 5. Apply Kubernetes manifests in order ───────────────────────────────────
info "Applying Kubernetes manifests..."
kubectl apply -f "$SCRIPT_DIR/00-namespace.yaml"
kubectl apply -f "$SCRIPT_DIR/01-configmap.yaml"
kubectl apply -f "$SCRIPT_DIR/02-postgres.yaml"
kubectl apply -f "$SCRIPT_DIR/03-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/04-deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/05-service.yaml"
kubectl apply -f "$SCRIPT_DIR/06-hpa.yaml"
ok "All manifests applied"

# ── 6. Wait for PostgreSQL to be ready ───────────────────────────────────────
info "Waiting for PostgreSQL pod to be ready (timeout 120s)..."
kubectl wait --namespace=cv-platform \
    --for=condition=ready pod \
    --selector=app=postgres \
    --timeout=120s
ok "PostgreSQL is ready"

# ── 7. Wait for the image-service to be ready ────────────────────────────────
info "Waiting for image-service pod to be ready (timeout 180s)..."
kubectl wait --namespace=cv-platform \
    --for=condition=ready pod \
    --selector=app=image-service \
    --timeout=180s
ok "image-service is ready"

# ── 8. Print service URL ─────────────────────────────────────────────────────
SERVICE_URL=$(minikube service image-service --namespace=cv-platform --url 2>/dev/null || true)

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo ""
ok "Deployment complete!"
echo ""
if [ -n "$SERVICE_URL" ]; then
    echo -e "  Service URL : ${GREEN}${SERVICE_URL}${NC}"
    echo -e "  Swagger UI  : ${GREEN}${SERVICE_URL}/docs${NC}"
    echo -e "  Health      : ${GREEN}${SERVICE_URL}/health${NC}"
else
    echo -e "  Run: ${YELLOW}minikube service image-service --namespace=cv-platform${NC}"
fi
echo ""
echo -e "  Run the demo: ${CYAN}./minikube/demo.sh${NC}"
echo ""
echo "════════════════════════════════════════════════════════════════════"
