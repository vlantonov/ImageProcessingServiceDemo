#!/usr/bin/env bash
# ─── minikube/observability/setup.sh ─────────────────────────────────────────
# Deploys the observability stack (Prometheus, Tempo, Loki, Promtail, Grafana)
# into a separate "observability" namespace in minikube.
#
# Prerequisites:
#   - minikube running (start it via ../setup.sh first)
#   - kubectl installed
#
# Usage:
#   cd <project-root>
#   ./minikube/observability/setup.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR/dashboards"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }

# ── 1. Create namespace ─────────────────────────────────────────────────────
info "Creating observability namespace..."
kubectl apply -f "$SCRIPT_DIR/00-namespace.yaml"
ok "Namespace created"

# ── 2. Generate Grafana dashboards ConfigMap from JSON files ─────────────────
info "Generating Grafana dashboards ConfigMap..."
kubectl create configmap grafana-dashboards \
    --namespace=observability \
    --from-file="$DASHBOARD_DIR/red-metrics.json" \
    --from-file="$DASHBOARD_DIR/traces.json" \
    --from-file="$DASHBOARD_DIR/logs.json" \
    --dry-run=client -o yaml | kubectl apply -f -
ok "Dashboard ConfigMap created"

# ── 3. Deploy observability stack ────────────────────────────────────────────
info "Deploying Prometheus..."
kubectl apply -f "$SCRIPT_DIR/01-prometheus.yaml"
ok "Prometheus deployed"

info "Deploying Tempo..."
kubectl apply -f "$SCRIPT_DIR/02-tempo.yaml"
ok "Tempo deployed"

info "Deploying Loki..."
kubectl apply -f "$SCRIPT_DIR/03-loki.yaml"
ok "Loki deployed"

info "Deploying Promtail..."
kubectl apply -f "$SCRIPT_DIR/04-promtail.yaml"
ok "Promtail deployed"

info "Deploying Grafana..."
kubectl apply -f "$SCRIPT_DIR/05-grafana.yaml"
ok "Grafana deployed"

# ── 4. Wait for pods ────────────────────────────────────────────────────────
info "Waiting for observability pods to be ready (timeout 180s)..."
kubectl wait --namespace=observability \
    --for=condition=ready pod \
    --selector=app=prometheus \
    --timeout=180s 2>/dev/null || true

kubectl wait --namespace=observability \
    --for=condition=ready pod \
    --selector=app=tempo \
    --timeout=180s 2>/dev/null || true

kubectl wait --namespace=observability \
    --for=condition=ready pod \
    --selector=app=loki \
    --timeout=180s 2>/dev/null || true

kubectl wait --namespace=observability \
    --for=condition=ready pod \
    --selector=app=grafana \
    --timeout=180s 2>/dev/null || true

ok "All observability pods ready"

# ── 5. Print access URLs ────────────────────────────────────────────────────
GRAFANA_URL=$(minikube service grafana --namespace=observability --url 2>/dev/null || true)

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo ""
ok "Observability stack deployed!"
echo ""
if [ -n "$GRAFANA_URL" ]; then
    echo -e "  Grafana      : ${GREEN}${GRAFANA_URL}${NC}  (admin/admin)"
    echo -e "  RED Metrics  : ${GREEN}${GRAFANA_URL}/d/image-service-red${NC}"
    echo -e "  Traces       : ${GREEN}${GRAFANA_URL}/d/image-service-traces${NC}"
    echo -e "  Logs         : ${GREEN}${GRAFANA_URL}/d/image-service-logs${NC}"
else
    echo -e "  Run: ${YELLOW}minikube service grafana --namespace=observability${NC}"
fi
echo ""
echo -e "  Prometheus   : port-forward with ${CYAN}kubectl port-forward -n observability svc/prometheus 9090${NC}"
echo ""
echo "════════════════════════════════════════════════════════════════════"
