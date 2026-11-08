#!/bin/bash
# ==============================================================================
# CloudDeploy - EC2 User Data Bootstrap Script
# Operating System: Ubuntu 24.04 / 22.04 LTS
# Idempotent bootstrap for Docker, Nginx reverse proxy, SSM, and CloudWatch Agent
# ==============================================================================

set -euo pipefail

exec > >(tee -a /var/log/clouddeploy-bootstrap.log) 2>&1
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Starting CloudDeploy EC2 bootstrap..."

# 1. System Package Updates & Prerequisites
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    jq \
    unzip \
    nginx

# 2. Install Docker Engine & Docker Compose Plugin
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Installing Docker..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# 3. Install AWS CLI v2
if ! command -v aws &> /dev/null; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Installing AWS CLI v2..."
    curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip -q awscliv2.zip
    ./aws/install
    rm -rf awscliv2.zip aws
fi

# 4. Install & Start Amazon CloudWatch Agent
echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Installing Amazon CloudWatch Agent..."
curl -s "https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb" -o "amazon-cloudwatch-agent.deb"
dpkg -i -E amazon-cloudwatch-agent.deb
rm -f amazon-cloudwatch-agent.deb

# 5. Create Application Directory Structure
mkdir -p /opt/clouddeploy/logs
mkdir -p /opt/clouddeploy/nginx

# 6. Configure Host Nginx Reverse Proxy
cat << 'EOF' > /etc/nginx/sites-available/clouddeploy
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 16M;

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 5s;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/clouddeploy /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
systemctl enable nginx

# 7. Provision Deployment Script on EC2 Host
cat << 'DEPLOY_SCRIPT_EOF' > /opt/clouddeploy/deploy.sh
#!/bin/bash
set -euo pipefail

ECR_REPOSITORY="${1:-}"
IMAGE_TAG="${2:-latest}"
AWS_REGION="${3:-us-east-1}"
APP_PORT="8000"
APP_DIR="/opt/clouddeploy"
LOG_FILE="/var/log/clouddeploy-deploy.log"

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

echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Authenticating with Amazon ECR..."
REGISTRY_HOST=$(echo "$ECR_REPOSITORY" | cut -d'/' -f1)
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY_HOST"

if [ -f "$APP_DIR/current_tag.txt" ]; then
    CURRENT_TAG=$(cat "$APP_DIR/current_tag.txt")
    echo "$CURRENT_TAG" > "$APP_DIR/previous_tag.txt"
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Recorded previous active tag: $CURRENT_TAG"
else
    echo "" > "$APP_DIR/previous_tag.txt"
fi

echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Pulling image: ${ECR_REPOSITORY}:${IMAGE_TAG}..."
docker pull "${ECR_REPOSITORY}:${IMAGE_TAG}"

if [ "$(docker ps -q -f name=clouddeploy-web)" ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Gracefully stopping current container..."
    docker stop --time 15 clouddeploy-web || true
    docker rm -f clouddeploy-web || true
fi

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

if [ "$HEALTHY" -eq 1 ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Deployment SUCCESSFUL! Health check returned HTTP 200."
    echo "$IMAGE_TAG" > "$APP_DIR/current_tag.txt"
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
DEPLOY_SCRIPT_EOF

# 8. Provision Rollback Script on EC2 Host
cat << 'ROLLBACK_SCRIPT_EOF' > /opt/clouddeploy/rollback.sh
#!/bin/bash
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

if [ "$(docker ps -q -f name=clouddeploy-web)" ]; then
    docker stop --time 10 clouddeploy-web || true
    docker rm -f clouddeploy-web || true
fi

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

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${APP_PORT}/health" || echo "000")
if [ "$HTTP_CODE" -eq 200 ]; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] Rollback SUCCESSFUL! Previous version restored and healthy (HTTP 200)."
    echo "$PREVIOUS_TAG" > "$APP_DIR/current_tag.txt"
    exit 0
else
    echo "CRITICAL: Rollback container failed health check (HTTP $HTTP_CODE)."
    exit 1
fi
ROLLBACK_SCRIPT_EOF

# 9. Set Permissions
chmod +x /opt/clouddeploy/*.sh
chown -R ubuntu:ubuntu /opt/clouddeploy

echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] CloudDeploy EC2 bootstrap completed successfully!"
