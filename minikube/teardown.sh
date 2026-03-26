#!/usr/bin/env bash
# ─── minikube/teardown.sh ────────────────────────────────────────────────────
# Removes all resources created by setup.sh.
#
# Usage:
#   ./minikube/teardown.sh           # delete namespace only
#   ./minikube/teardown.sh --all     # also stop minikube
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }

info "Deleting cv-platform namespace and all its resources..."
kubectl delete namespace cv-platform --ignore-not-found=true
ok "Namespace cv-platform deleted"

if [ "${1:-}" = "--all" ]; then
    info "Stopping minikube..."
    minikube stop
    ok "Minikube stopped"
    echo ""
    echo -e "  To fully delete the cluster: ${YELLOW}minikube delete${NC}"
fi

echo ""
ok "Teardown complete"
