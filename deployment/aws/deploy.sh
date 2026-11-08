#!/bin/bash
# ==============================================================================
# CloudDeploy - Remote EC2 Container Rollout & Health Verification Script
# ==============================================================================

set -euo pipefail

ECR_REPOSITORY="${1:-}"
IMAGE_TAG="${2:-latest}"
AWS_REGION="${3:-us-east-1}"
APP_PORT="8000"
APP_DIR="/opt/clouddeploy"
LOG_FILE="/var/log/clouddeploy-deploy.log"
HISTORY_FILE="$APP_DIR/deployment_history.json"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "======================================================================"
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Starting CloudDeploy Deployment"
echo "Target Image: ${ECR_REPOSITORY}:${IMAGE_TAG}"
echo "Region:       ${AWS_REGION}"
echo "======================================================================"

if [ -z "$ECR_REPOSITORY" ]; then
    echo "ERROR: ECR_REPOSITORY argument is required."
    exit 1
fi

mkdir -p "$APP_DIR"

# 1. Authenticate Docker to Amazon ECR
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Authenticating with Amazon ECR..."
REGISTRY_HOST=$(echo "$ECR_REPOSITORY" | cut -d'/' -f1)
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY_HOST"

# 2. Record previous image tag for rollback safety
if [ -f "$APP_DIR/current_tag.txt" ]; then
    CURRENT_TAG=$(cat "$APP_DIR/current_tag.txt")
    echo "$CURRENT_TAG" > "$APP_DIR/previous_tag.txt"
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Recorded previous active tag: $CURRENT_TAG"
else
    echo "" > "$APP_DIR/previous_tag.txt"
fi

# 3. Pull Target Docker Image
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Pulling image: ${ECR_REPOSITORY}:${IMAGE_TAG}..."
docker pull "${ECR_REPOSITORY}:${IMAGE_TAG}"

# 4. Stop and remove existing container if running
if [ "$(docker ps -q -f name=clouddeploy-web)" ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Gracefully stopping current container..."
    docker stop --time 15 clouddeploy-web || true
    docker rm -f clouddeploy-web || true
fi

# 5. Start New Application Container
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Starting updated container: clouddeploy-web..."
docker run -d \
    --name clouddeploy-web \
    --restart unless-stopped \
    -p "127.0.0.1:${APP_PORT}:8000" \
    -e APP_NAME="CloudDeploy" \
    -e APP_VERSION="${IMAGE_TAG}" \
    -e ENVIRONMENT="production" \
    -e DEPLOYMENT_ID="${IMAGE_TAG}" \
    -e AWS_REGION="${AWS_REGION}" \
    "${ECR_REPOSITORY}:${IMAGE_TAG}"

# 6. Perform Automated Health Check Verification
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Verifying container health via http://127.0.0.1:${APP_PORT}/health..."
MAX_ATTEMPTS=6
HEALTHY=0

for i in $(seq 1 $MAX_ATTEMPTS); do
    sleep 5
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${APP_PORT}/health" || echo "000")
    echo "Health probe attempt $i/$MAX_ATTEMPTS: HTTP $HTTP_CODE"

    if [ "$HTTP_CODE" -eq 200 ]; then
        HEALTHY=1
        break
    fi
done

# 7. Evaluate Health & Execute Rollback if necessary
if [ "$HEALTHY" -eq 1 ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Deployment SUCCESSFUL! Health check returned HTTP 200."
    echo "$IMAGE_TAG" > "$APP_DIR/current_tag.txt"

    # Record successful deployment in history JSON
    TIMESTAMP=$(date -u +'%Y-%m-%d %H:%M:%S UTC')
    python3 -c "
import json, sys
entry = {
    'deployment_id': sys.argv[1],
    'version': sys.argv[1],
    'timestamp': sys.argv[2],
    'environment': 'production',
    'status': 'SUCCESS',
    'details': 'Automated rollout verified'
}
history = []
try:
    with open('$HISTORY_FILE', 'r') as f:
        history = json.load(f)
except Exception:
    pass
history.insert(0, entry)
with open('$HISTORY_FILE', 'w') as f:
    json.dump(history[:10], f, indent=2)
" "$IMAGE_TAG" "$TIMESTAMP" 2>/dev/null || true

    # Clean up obsolete image layers
    docker image prune -f || true
    exit 0
else
    echo "CRITICAL: Health check FAILED after $MAX_ATTEMPTS attempts."
    echo "Initiating automated rollback to previous operational state..."
    if [ -f "$APP_DIR/rollback.sh" ]; then
        bash "$APP_DIR/rollback.sh" "$ECR_REPOSITORY" "$AWS_REGION"
    else
        echo "ERROR: Rollback script not found at $APP_DIR/rollback.sh"
    fi
    exit 1
fi
