# CloudDeploy - Automated Testing Specification & Verification Report

This document details the automated testing architecture, test categories, coverage metrics, and verification procedures for **CloudDeploy**.

---

## 1. Test Suite Summary

- **Test Framework:** Pytest 8.2.2
- **Coverage Plugin:** pytest-cov 5.0.0
- **Style & Quality Linter:** Flake8 7.1.0
- **Total Test Cases:** **37**
- **Pass Rate:** **37/37 Passed (100%)**
- **Statement Coverage:** **100% (359/359 statements)** across all application modules.
- **Flake8 Violations:** **0 violations** (PEP8 compliant with 120-character line length limit).

---

## 2. Code Coverage Matrix

```
---------- coverage: platform win32, python 3.11.5-final-0 -----------
Name              Stmts   Miss  Cover   Missing
-----------------------------------------------
app\__init__.py      75      0   100%
app\config.py        31      0   100%
app\routes.py       253      0   100%
-----------------------------------------------
TOTAL               359      0   100%
============================= 37 passed in 2.28s ==============================
```

---

## 3. Test Categories & Verification Scope

### 3.1 Web Application Routes & Templates
- `test_homepage_status_and_content`: Verifies `GET /` returns HTTP 200, hero elements, and pipeline overview.
- `test_deployment_page`: Validates `GET /deployment` renders Sections A through H, KPI cards, and diagnostics.
- `test_about_page`: Ensures `GET /about` returns HTTP 200 and architecture specifications.

### 3.2 Health Check & Service Metadata Endpoints
- `test_health_endpoint_status`: Asserts `GET /health` returns HTTP 200.
- `test_health_endpoint_payload`: Validates required JSON keys (`status`, `app_name`, `version`, `timestamp`, `hosting_provider`, `uptime_seconds`) and ISO 8601 formatting.
- `test_api_info_endpoint`: Confirms non-sensitive operational metadata is exposed without leaking keys or credentials.

### 3.3 Consolidated Telemetry & System Monitoring
- `test_api_system_metrics`: Tests `/api/system-metrics` backward-compatible endpoint.
- `test_api_monitoring`: Verifies `/api/monitoring` consolidated metrics payload (system, docker, hosting, uptime).
- `test_get_system_metrics_disk_and_mem`: Tests real disk calculations and `/proc/meminfo` memory parsing under success and error conditions.
- `test_get_system_metrics_meminfo_exception`: Validates graceful fallback when memory stats are unavailable.
- `test_get_uptime_seconds_helper`: Validates uptime calculation and fallback when `START_TIME` is missing.
- `test_is_running_in_docker_helper`: Mocks `/.dockerenv` and `/proc/self/cgroup` to test container detection and permission error handling.

### 3.4 GitHub Actions REST API Telemetry
- `test_parse_duration_seconds`: Tests ISO timestamp parsing and duration calculation in seconds.
- `test_fetch_github_workflows_success`: Mocks GitHub Actions API response, verifying workflow run extraction, duration calculation, and 30-second in-memory caching.
- `test_fetch_github_workflows_errors`: Tests graceful handling of HTTP 403 (rate limit exceeded), HTTP 404 (repo not found), HTTP 500 (API error), and network `URLError`.
- `test_fetch_github_workflows_fallback_with_existing_cache`: Verifies cached telemetry is returned with a warning flag during transient upstream API outages.
- `test_api_github_workflows_endpoint`: Tests `GET /api/github/workflows` HTTP endpoint.
- `test_get_cicd_pipeline_status`: Verifies backwards-compatible CI/CD status extractor.

### 3.5 Render Cloud Deployment History
- `test_fetch_render_deployments`: Tests unconfigured mode (returns honest status and native Git deployment indicator) and authenticated mode (parses Render deploy records).
- `test_api_deployments_endpoint`: Verifies `GET /api/deployments` HTTP endpoint.
- `test_get_deployment_history_file`: Tests reading filesystem deployment records.
- `test_get_deployment_history_corrupted_fallback`: Verifies graceful fallback on corrupted JSON records.

### 3.6 Alerts & Notifications
- `test_api_alerts_endpoint`: Tests `GET /api/alerts` HTTP endpoint.
- `test_disk_alert_rendered_in_dashboard`: Validates high storage utilization alert when disk usage exceeds 85%.
- `test_get_active_alerts_variations`: Tests alert generation on CI pipeline failure, container mode, and AWS disconnection.

### 3.7 Security, Logging & Error Handling
- `test_security_headers_present`: Validates injection of `X-Frame-Options`, `X-Content-Type-Options`, and `X-XSS-Protection`.
- `test_api_logs`: Verifies in-memory ring buffer log streaming and confirms automatic redaction of `SECRET_KEY` and API tokens.
- `test_recent_logs_handler_error_handling`: Tests error resilience in `RecentLogsHandler.emit()`.
- `test_404_not_found_html`: Tests 404 page rendering for browser requests.
- `test_404_not_found_json`: Tests 404 JSON response for API requests (`Accept: application/json`).
- `test_500_error_handling_json`: Tests 500 error handler returning structured JSON.
- `test_500_error_handling_html`: Tests 500 error handler returning styled HTML.
- `test_error_trigger_forbidden_when_not_debug`: Asserts `/error-trigger` is strictly forbidden in production.
- `test_create_app_env_overrides`: Tests configuration overrides via environment variables.
- `test_create_app_default_config`: Confirms production configuration default.

---

## 4. Running the Tests Locally

```powershell
# Run the complete test suite with coverage report
python -m pytest -v --cov=app --cov-report=term-missing

# Enforce PEP8 code quality linting
python -m flake8 app/ tests/ --count --max-line-length=120 --statistics
```
