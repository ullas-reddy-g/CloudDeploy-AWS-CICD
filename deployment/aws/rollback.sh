#!/bin/bash
# ==============================================================================
# CloudDeploy - Automated Container Rollback Handler
# ==============================================================================

set -euo pipefail

ECR_REPOSITORY="${1:-}"
AWS_REGION="${2:-us-east-1}"
APP_PORT="8000"
APP_DIR="/opt/clouddeploy"
LOG_FILE="/var/log/clouddeploy-deploy.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "======================================================================"
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] INITIATING ROLLBACK PROCEDURE"
echo "======================================================================"

if [ ! -f "$APP_DIR/previous_tag.txt" ]; then
    echo "CRITICAL: No previous tag record found. Cannot execute automated rollback."
    exit 1
fi

PREVIOUS_TAG=$(cat "$APP_DIR/previous_tag.txt" | tr -d '[:space:]')

if [ -z "$PREVIOUS_TAG" ]; then
    echo "CRITICAL: Previous tag is empty. No previous stable version recorded."
    exit 1
fi

echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Rolling back to previous stable image: ${ECR_REPOSITORY}:${PREVIOUS_TAG}"

# Stop and remove unhealthy container
if [ "$(docker ps -q -f name=clouddeploy-web)" ]; then
    docker stop --time 10 clouddeploy-web || true
    docker rm -f clouddeploy-web || true
fi

# Run previous stable container
docker run -d \
    --name clouddeploy-web \
    --restart unless-stopped \
    -p "127.0.0.1:${APP_PORT}:8000" \
    -e APP_NAME="CloudDeploy" \
    -e APP_VERSION="${PREVIOUS_TAG}" \
    -e ENVIRONMENT="production" \
    -e DEPLOYMENT_ID="${PREVIOUS_TAG}-rollback" \
    -e AWS_REGION="${AWS_REGION}" \
    "${ECR_REPOSITORY}:${PREVIOUS_TAG}"

sleep 5

# Verify rollback container health
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${APP_PORT}/health" || echo "000")
if [ "$HTTP_CODE" -eq 200 ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Rollback SUCCESSFUL! Previous version restored and healthy (HTTP 200)."
    echo "$PREVIOUS_TAG" > "$APP_DIR/current_tag.txt"
    exit 0
else
    echo "CRITICAL: Rollback container failed health check (HTTP $HTTP_CODE)."
    exit 1
fi
