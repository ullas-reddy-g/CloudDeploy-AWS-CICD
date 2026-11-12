# Project Evidence & Screenshot Catalog

This directory contains visual validation evidence for the **CloudDeploy** automated continuous integration and continuous deployment pipeline.

---

## Required Visual Evidence Catalog

| # | Evidence File | Component / View | Target URL / Command | Verification Purpose |
|---|---|---|---|---|
| 1 | `homepage.png` | Application Homepage | `https://clouddeploy-aws-cicd.onrender.com/` | Validates public HTTPS access, hero KPIs, live uptime, and quick navigation. |
| 2 | `dashboard.png` | Monitoring Dashboard | `https://clouddeploy-aws-cicd.onrender.com/deployment` | Validates live telemetry, Sections A-H, cgroup limits, and streaming logs. |
| 3 | `docker-container-status.png` | Docker Container & Privilege | `https://clouddeploy-aws-cicd.onrender.com/api/info` | Proves `is_container: true` and unprivileged execution (`UID 10001 / clouddeploy`). |
| 4 | `github-actions-ci.png` | GitHub Actions CI Run | `https://github.com/ullas-reddy-g/CloudDeploy-AWS-CICD/actions` | Confirms green status for Linting (Flake8), Pytest (100% cov), and Docker build. |
| 5 | `github-actions-cd.png` | GitHub Actions CD Run | `https://github.com/ullas-reddy-g/CloudDeploy-AWS-CICD/actions` | Confirms green CD execution (`CD Pipeline - Deploy to Render`) and commit SHA polling. |
| 6 | `render-live-deployment.png` | Render Service & Runtime | `https://dashboard.render.com` or `/api/deployments` | Confirms active Web Service (`srv-dbqn4es9v7es73d40jag`) on branch `main`. |
| 7 | `architecture-diagram.png` | Architecture Specification | `https://clouddeploy-aws-cicd.onrender.com/about` | Demonstrates 3-tier architecture, non-root security model, and AWS extension. |
| 8 | `test-coverage.png` | Test Results & Coverage | `python -m pytest -v --cov=app` | Proves 40/40 tests passing with 100% statement coverage (461/461 statements). |

---

## Instructions for Capturing Visual Evidence

Because browser window rendering is restricted in headless command-line development environments, capture high-resolution desktop screenshots using your preferred browser:

1. **Application Homepage (`homepage.png`):**
   - Navigate to [https://clouddeploy-aws-cicd.onrender.com/](https://clouddeploy-aws-cicd.onrender.com/).
   - Capture full page showing navigation, hero card with status badge, and features.
   - Save to `docs/screenshots/homepage.png`.

2. **Monitoring Dashboard (`dashboard.png`):**
   - Navigate to [https://clouddeploy-aws-cicd.onrender.com/deployment](https://clouddeploy-aws-cicd.onrender.com/deployment).
   - Set viewport to 1920x1080 (or Full Page capture).
   - Save the screenshot to `docs/screenshots/dashboard.png`.

3. **Docker Container Status (`docker-container-status.png`):**
   - Navigate to [https://clouddeploy-aws-cicd.onrender.com/api/info](https://clouddeploy-aws-cicd.onrender.com/api/info) or Section B of the dashboard.
   - Capture the verified non-root UID 10001 badge and container status indicator.
   - Save to `docs/screenshots/docker-container-status.png`.

4. **GitHub Actions CI (`github-actions-ci.png`):**
   - Open [GitHub Actions Console](https://github.com/ullas-reddy-g/CloudDeploy-AWS-CICD/actions).
   - Click the latest run of `CI Pipeline - Build & Test` (Run #43261813459).
   - Take a screenshot displaying both jobs (`Lint & Pytest Suite` and `Container Build & Runtime Verification`) marked green with checkmarks.
   - Save to `docs/screenshots/github-actions-ci.png`.

5. **GitHub Actions CD (`github-actions-cd.png`):**
   - In GitHub Actions Console, click the latest run of `CD Pipeline - Deploy to Render` (Run #43262049166).
   - Capture the green workflow execution and commit SHA match log.
   - Save to `docs/screenshots/github-actions-cd.png`.

6. **Render Successful Deployment (`render-live-deployment.png`):**
   - Open Render Cloud dashboard at [https://dashboard.render.com](https://dashboard.render.com) for service `srv-dbqn4es9v7es73d40jag`.
   - Capture the deployment log showing "Deploy live for commit 43e8971".
   - Save to `docs/screenshots/render-live-deployment.png`.

7. **Architecture Diagram (`architecture-diagram.png`):**
   - Open [https://clouddeploy-aws-cicd.onrender.com/about](https://clouddeploy-aws-cicd.onrender.com/about).
   - Scroll to the interactive architecture card and system topology.
   - Save to `docs/screenshots/architecture-diagram.png`.

8. **Test Results and Coverage (`test-coverage.png`):**
   - In your local terminal, run:
     ```powershell
     python -m pytest -v --cov=app --cov-report=term-missing
     ```
   - Capture the terminal output displaying all 40 tests passed and `TOTAL 461 0 100%`.
   - Save to `docs/screenshots/test-coverage.png`.
