# Project Evidence & Screenshot Catalog

This directory contains visual validation evidence for the **CloudDeploy** automated continuous integration and continuous deployment pipeline.

---

## Required Visual Evidence Catalog

| Evidence File | Component / View | Target URL / Command | Verification Purpose |
|---|---|---|---|
| `dashboard.png` | Primary Monitoring Dashboard | `https://clouddeploy-aws-cicd.onrender.com/deployment` or `http://localhost:8000/deployment` | Validates live telemetry, Sections A-H, real-time GitHub Actions status, Render deployment indicator, and streaming logs. |
| `deployment-info.png` | Deployment Diagnostics & Metadata | `https://clouddeploy-aws-cicd.onrender.com/api/info` & `/health` | Demonstrates JSON API payloads, zero secret leakage, and operational health probes. |
| `architecture.png` | System Architecture & Security Spec | `https://clouddeploy-aws-cicd.onrender.com/about` | Documents containerization stack, non-root execution, and CI/CD topology. |
| `github-actions-ci.png` | GitHub Actions CI Execution | `https://github.com/ullas-reddy-g/CloudDeploy-AWS-CICD/actions` | Confirms green build status for Linting (Flake8), Pytest (100% statement coverage), Docker Buildx, and Compose runtime verification. |
| `render-live-deployment.png` | Render Cloud Web Service Dashboard | `https://dashboard.render.com` | Confirms active Web Service linked to repository `ullas-reddy-g/CloudDeploy-AWS-CICD` on branch `main`. |
| `docker-runtime.png` | Docker & Nginx Reverse Proxy Runtime | `docker compose ps` / `curl -I http://localhost:80/health` | Validates local multi-container orchestration, unprivileged user (UID 10001), and Nginx port 80 routing. |

---

## Instructions for Capturing Visual Evidence

Because browser window rendering is restricted in headless command-line development environments, capture high-resolution desktop screenshots using your preferred browser:

1. **Production Dashboard (`dashboard.png`):**
   - Navigate to [https://clouddeploy-aws-cicd.onrender.com/deployment](https://clouddeploy-aws-cicd.onrender.com/deployment).
   - Set viewport to 1920x1080 (or Full Page capture).
   - Save the screenshot to `docs/screenshots/dashboard.png`.

2. **GitHub Actions Green CI Run (`github-actions-ci.png`):**
   - Open [GitHub Actions Console](https://github.com/ullas-reddy-g/CloudDeploy-AWS-CICD/actions).
   - Click the latest run of `CI Pipeline - Build & Test`.
   - Take a screenshot displaying both jobs (`Lint & Pytest Suite` and `Container Build & Runtime Verification`) marked green with checkmarks.
   - Save to `docs/screenshots/github-actions-ci.png`.

3. **Render Live Deployment (`render-live-deployment.png`):**
   - Open [https://clouddeploy-aws-cicd.onrender.com](https://clouddeploy-aws-cicd.onrender.com).
   - Capture the hero section with the "Render Cloud Live Production" indicator.
   - Save to `docs/screenshots/render-live-deployment.png`.

4. **Docker Runtime Verification (`docker-runtime.png`):**
   - In your local terminal, run:
     ```bash
     docker compose up -d
     docker ps
     curl -i http://localhost:80/health
     ```
   - Capture the terminal output showing both `clouddeploy-web` and `clouddeploy-nginx` running healthy.
   - Save to `docs/screenshots/docker-runtime.png`.
