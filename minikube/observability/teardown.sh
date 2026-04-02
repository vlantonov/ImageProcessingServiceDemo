#!/usr/bin/env bash
# ─── minikube/observability/teardown.sh ──────────────────────────────────────
# Removes all observability resources.
#
# Usage:
#   ./minikube/observability/teardown.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }

info "Deleting observability namespace and all its resources..."
kubectl delete namespace observability --ignore-not-found=true

# Clean up cluster-wide RBAC resources
kubectl delete clusterrole prometheus --ignore-not-found=true
kubectl delete clusterrolebinding prometheus --ignore-not-found=true
kubectl delete clusterrole promtail --ignore-not-found=true
kubectl delete clusterrolebinding promtail --ignore-not-found=true

ok "Observability stack removed"
