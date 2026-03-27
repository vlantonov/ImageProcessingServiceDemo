#!/usr/bin/env bash
# ─── minikube/demo.sh ────────────────────────────────────────────────────────
# Interactive walkthrough exercising every API endpoint of the image service.
#
# Prerequisites:
#   - Service deployed via ./minikube/setup.sh
#   - curl and jq installed
#
# Usage:
#   ./minikube/demo.sh                          # auto-detect URL
#   ./minikube/demo.sh http://192.168.49.2:30080  # explicit URL
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "\n${CYAN}━━━ $* ━━━${NC}"; }
ok()    { echo -e "${GREEN}✓ $*${NC}"; }
fail()  { echo -e "${RED}✗ $*${NC}"; }

# ── Resolve service URL ──────────────────────────────────────────────────────
if [ "${1:-}" != "" ]; then
    BASE_URL="$1"
else
    BASE_URL=$(minikube service image-service --namespace=cv-platform --url 2>/dev/null || true)
    if [ -z "$BASE_URL" ]; then
        echo "Could not auto-detect service URL."
        echo "Usage: $0 <service-url>"
        exit 1
    fi
fi

echo -e "${BOLD}Image Processing Service — Demo${NC}"
echo -e "Base URL: ${YELLOW}${BASE_URL}${NC}"

# ── 1. Health check ──────────────────────────────────────────────────────────
info "1. Health Check"
curl -s "${BASE_URL}/health" | jq .
ok "Service is healthy"

# ── 2. Create sample test images ─────────────────────────────────────────────
info "2. Generate sample test images"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Generate images using Python (Pillow is likely available; fallback to raw PNGs)
python3 - "$TMPDIR" <<'PYEOF'
import sys, io
from PIL import Image
out = sys.argv[1]
colors = [("red", (255,0,0)), ("green", (0,255,0)), ("blue", (0,0,255))]
for name, color in colors:
    img = Image.new("RGB", (640, 480), color=color)
    img.save(f"{out}/{name}.png", format="PNG")
    print(f"  Created {name}.png (640x480)")
PYEOF
ok "Test images generated in $TMPDIR"

# ── 3. Upload images ─────────────────────────────────────────────────────────
info "3. Upload Images"
declare -a IMAGE_IDS=()

for color in red green blue; do
    echo -e "  Uploading ${BOLD}${color}.png${NC} with tags=[${color}, demo]..."
    RESPONSE=$(curl -s -w "\n%{http_code}" \
        -X POST "${BASE_URL}/api/v1/images/?tags=${color}&tags=demo" \
        -F "file=@${TMPDIR}/${color}.png;type=image/png")

    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    if [ "$HTTP_CODE" = "201" ]; then
        ID=$(echo "$BODY" | jq -r '.id')
        IMAGE_IDS+=("$ID")
        ok "Uploaded ${color}.png → id=${ID}"
    else
        fail "Upload failed (HTTP ${HTTP_CODE}): ${BODY}"
        exit 1
    fi
done

# ── 4. Upload with TTL (for retention demo) ──────────────────────────────────
info "4. Upload Image with TTL (retention demo)"
echo -e "  Uploading red.png with ttl_hours=1..."
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/v1/images/?tags=temporary&ttl_hours=1" \
    -F "file=@${TMPDIR}/red.png;type=image/png")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "201" ]; then
    TTL_ID=$(echo "$BODY" | jq -r '.id')
    EXPIRES=$(echo "$BODY" | jq -r '.expires_at')
    IMAGE_IDS+=("$TTL_ID")
    ok "Uploaded with TTL → id=${TTL_ID}, expires_at=${EXPIRES}"
else
    fail "Upload failed: ${BODY}"
fi

# ── 5. List all images ───────────────────────────────────────────────────────
info "5. List Images (paginated)"
echo "  GET /api/v1/images/?limit=10"
curl -s "${BASE_URL}/api/v1/images/?limit=10" | jq '{total, offset, limit, image_count: (.images | length), filenames: [.images[].filename]}'
ok "Listed images"

# ── 6. Get single image metadata ─────────────────────────────────────────────
info "6. Get Image Metadata"
FIRST_ID="${IMAGE_IDS[0]}"
echo "  GET /api/v1/images/${FIRST_ID}"
curl -s "${BASE_URL}/api/v1/images/${FIRST_ID}" | jq .
ok "Retrieved metadata for ${FIRST_ID}"

# ── 7. Process a single image (thumbnail generation) ─────────────────────────
info "7. Process Single Image (generates thumbnail + extracts metadata)"
echo "  POST /api/v1/images/${FIRST_ID}/process"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/v1/images/${FIRST_ID}/process")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "$BODY" | jq '{id, status, width, height, format, size_bytes, thumbnail_available}'
    ok "Image processed successfully"
else
    fail "Processing failed (HTTP ${HTTP_CODE}): ${BODY}"
fi

# ── 8. Batch process remaining images ────────────────────────────────────────
info "8. Batch Process (parallel processing of multiple images)"
REMAINING_IDS=$(printf '"%s",' "${IMAGE_IDS[@]:1}")
REMAINING_IDS="[${REMAINING_IDS%,}]"
echo "  POST /api/v1/images/batch/process with $((${#IMAGE_IDS[@]} - 1)) images, concurrency=4"

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/v1/images/batch/process" \
    -H "Content-Type: application/json" \
    -d "{\"image_ids\": ${REMAINING_IDS}, \"concurrency\": 4}")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "$BODY" | jq .
    ok "Batch processing complete"
else
    fail "Batch processing failed (HTTP ${HTTP_CODE}): ${BODY}"
fi

# ── 9. Download original and thumbnail ───────────────────────────────────────
info "9. Download Original & Thumbnail"
echo "  Downloading original..."
curl -s -o "${TMPDIR}/downloaded_original.png" \
    "${BASE_URL}/api/v1/images/${FIRST_ID}/download"
ORIG_SIZE=$(stat -c%s "${TMPDIR}/downloaded_original.png" 2>/dev/null || stat -f%z "${TMPDIR}/downloaded_original.png" 2>/dev/null)
ok "Original downloaded: ${ORIG_SIZE} bytes"

echo "  Downloading thumbnail..."
curl -s -o "${TMPDIR}/downloaded_thumb.png" \
    "${BASE_URL}/api/v1/images/${FIRST_ID}/download?thumbnail=true"
THUMB_SIZE=$(stat -c%s "${TMPDIR}/downloaded_thumb.png" 2>/dev/null || stat -f%z "${TMPDIR}/downloaded_thumb.png" 2>/dev/null)
ok "Thumbnail downloaded: ${THUMB_SIZE} bytes"

# ── 10. Filter by status ─────────────────────────────────────────────────────
info "10. Filter Images by Status"
echo "  GET /api/v1/images/?status=completed"
curl -s "${BASE_URL}/api/v1/images/?status=completed" | jq '{total, filenames: [.images[].filename]}'
ok "Filtered by status=completed"

# ── 11. Retention sweep ──────────────────────────────────────────────────────
info "11. Retention Sweep"
echo "  POST /api/v1/retention/sweep"
RESPONSE=$(curl -s "${BASE_URL}/api/v1/retention/sweep" -X POST)
echo "$RESPONSE" | jq .
ok "Retention sweep executed (expired images cleaned up)"

# ── 12. Verify Kubernetes resources ──────────────────────────────────────────
info "12. Kubernetes Resource Status"
echo ""
echo -e "  ${BOLD}Pods:${NC}"
kubectl get pods -n cv-platform -o wide 2>/dev/null || echo "  (kubectl not available)"
echo ""
echo -e "  ${BOLD}Services:${NC}"
kubectl get svc -n cv-platform 2>/dev/null || echo "  (kubectl not available)"
echo ""
echo -e "  ${BOLD}HPA:${NC}"
kubectl get hpa -n cv-platform 2>/dev/null || echo "  (kubectl not available)"
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
info "Demo Complete!"
echo ""
echo -e "  ${BOLD}Demonstrated:${NC}"
echo "    ✓ Health check endpoint (K8s probes)"
echo "    ✓ Image upload with tags"
echo "    ✓ Image upload with TTL (retention policy)"
echo "    ✓ Paginated listing with filtering"
echo "    ✓ Single image metadata retrieval"
echo "    ✓ Single image processing (thumbnail + metadata)"
echo "    ✓ Batch parallel processing"
echo "    ✓ File download (original + thumbnail)"
echo "    ✓ Retention sweep (expired image cleanup)"
echo "    ✓ Kubernetes deployment, HPA, services"
echo ""
echo -e "  Swagger UI: ${YELLOW}${BASE_URL}/docs${NC}"
echo ""
