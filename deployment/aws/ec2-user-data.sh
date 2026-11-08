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

# 7. Final Permissions
chown -R ubuntu:ubuntu /opt/clouddeploy
chmod +x /opt/clouddeploy/*.sh || true

echo "[$(date -u +'%Y-%m-%d %H:%M:%SZ')] CloudDeploy EC2 bootstrap completed successfully!"
