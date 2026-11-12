# CloudDeploy - Deployment & Operational Guide

This document outlines the deployment processes for **CloudDeploy**, covering the active production deployment on **Render Cloud**, local Docker runtime verification, and the optional enterprise **AWS infrastructure extension**.

---

## 1. Production Hosting: Render Cloud (Active Platform)

The application is deployed on **Render Cloud** (Free Plan) and accessible publicly:
- **Production URL:** [https://clouddeploy-aws-cicd.onrender.com](https://clouddeploy-aws-cicd.onrender.com)
- **Health Check Endpoint:** [https://clouddeploy-aws-cicd.onrender.com/health](https://clouddeploy-aws-cicd.onrender.com/health)
- **Service Metadata:** [https://clouddeploy-aws-cicd.onrender.com/api/info](https://clouddeploy-aws-cicd.onrender.com/api/info)
- **Monitoring Dashboard:** [https://clouddeploy-aws-cicd.onrender.com/deployment](https://clouddeploy-aws-cicd.onrender.com/deployment)

### 1.1 Native Automatic Git-Push Deployment
Render natively monitors the GitHub repository `ullas-reddy-g/CloudDeploy-AWS-CICD` on the `main` branch.
1. When a commit is pushed to `main`, Render detects the push.
2. Render initiates a Docker build using the root `Dockerfile`.
3. Render starts the Gunicorn container binding to port `8000` (or the dynamic `$PORT` environment variable).
4. Zero downtime or minimal cutover occurs once health probes respond.

### 1.2 CI-Gated Deploy Hook (Optional Advanced Setup)
To strictly gate Render deployments behind passing GitHub Actions tests:
1. In Render Dashboard, navigate to **Settings &rarr; Deploy Hook**.
2. Copy the private Webhook URL (format: `https://api.render.com/deploy/srv-xxxxxx?key=yyyyyy`).
3. In GitHub, navigate to **Settings &rarr; Secrets and variables &rarr; Actions**.
4. Add a repository secret named `RENDER_DEPLOY_HOOK` containing the URL.
5. In Render settings, disable "Auto-Deploy" so that only the GitHub Actions CD workflow triggers deployments after all tests pass!

---

## 2. Local Development & Docker Verification

### 2.1 Running Locally with Python
```powershell
# 1. Clone repository
git clone https://github.com/ullas-reddy-g/CloudDeploy-AWS-CICD.git
cd CloudDeploy

# 2. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install development dependencies
pip install --upgrade pip
pip install -r requirements-dev.txt

# 4. Run test suite
python -m pytest -v --cov=app --cov-report=term-missing

# 5. Start development server
python -c "from app import create_app; app = create_app('development'); app.run(host='0.0.0.0', port=8000, debug=True)"
```
Access the application at `http://localhost:8000`.

### 2.2 Running Standalone Docker Container
```bash
# Build the container image
docker build -t clouddeploy:latest .

# Run container as isolated background process
docker run -d --name clouddeploy-app -p 8000:8000 clouddeploy:latest

# Verify health status
curl -i http://localhost:8000/health

# Verify unprivileged user (UID 10001)
docker exec clouddeploy-app id -u
# Output: 10001

# Cleanup
docker stop clouddeploy-app && docker rm clouddeploy-app
```

### 2.3 Running with Docker Compose & Nginx Proxy
```bash
# Launch multi-container setup (Flask + Nginx reverse proxy)
docker compose up -d --build

# Verify container statuses
docker compose ps

# Test reverse proxy on port 80
curl -i http://localhost:80/health

# Teardown
docker compose down
```

---

## 3. Optional Enterprise Deployment on AWS (Architecture Extension)

All AWS infrastructure artifacts are provided in `deployment/aws/` for academic demonstration and enterprise scalability. **No billable AWS resources are required for active operation.**

### 3.1 Provisioning Components
1. **Amazon ECR:** Run `deployment/scripts/ecr-setup.sh` to provision an immutable, encrypted container repository.
2. **IAM OIDC Role:** Deploy `deployment/aws/github-oidc-trust-policy.json` and `deployment/aws/iam-policy.json` to allow GitHub Actions passwordless STS role assumption.
3. **EC2 Bootstrap:** Launch an Ubuntu 24.04 EC2 instance attaching `deployment/aws/ec2-user-data.sh`, which automatically provisions Docker, Nginx, SSM Agent, and CloudWatch Agent.
4. **Trigger Deployment:** Trigger the manual workflow `.github/workflows/aws-deploy-optional.yml` via GitHub Actions `workflow_dispatch`.
5. **Zero-Cost Teardown:** Execute `deployment/aws/cleanup.sh` to terminate all AWS resources immediately post-testing.
