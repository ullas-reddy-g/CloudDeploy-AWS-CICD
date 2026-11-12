import json
import logging
import os
import urllib.error
from unittest.mock import patch, mock_open, MagicMock
from app import create_app
from app.routes import (
    get_uptime_seconds,
    is_running_in_docker,
    get_runtime_privilege,
    get_container_resource_limits,
    get_system_metrics,
    get_aws_cloud_status,
    get_cicd_pipeline_status,
    get_deployment_history,
    parse_duration_seconds,
    fetch_github_workflows,
    fetch_render_deployments,
    get_active_alerts,
)


def test_homepage_status_and_content(client):
    """Test that the homepage returns HTTP 200 and expected branding."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"CloudDeploy" in response.data
    assert b"Automated CI/CD Pipeline Workflow" in response.data


def test_deployment_page(client):
    """Test that the cloud deployment dashboard page returns HTTP 200 and required sections."""
    response = client.get("/deployment")
    assert response.status_code == 200
    assert b"Cloud Deployment & Monitoring Dashboard" in response.data
    assert b"test-ci-build-1" in response.data
    assert b"Section B: Docker Container Monitoring" in response.data
    assert b"Section C: AWS Cloud Infrastructure" in response.data
    assert b"Section D: CI/CD Automation Pipeline" in response.data
    assert b"Section E: Deployment History" in response.data
    assert b"Section F: Recent Application Logs" in response.data


def test_about_page(client):
    """Test that the about page returns HTTP 200."""
    response = client.get("/about")
    assert response.status_code == 200
    assert b"Architecture & Engineering Specification" in response.data
    assert b"Zero Long-Lived Credentials" in response.data


def test_404_not_found_html(client):
    """Test that an invalid route returns HTTP 404 HTML response."""
    response = client.get("/non-existent-route-xyz")
    assert response.status_code == 404
    assert b"Page or Endpoint Not Found" in response.data


def test_404_not_found_json(client):
    """Test that an invalid API route returns HTTP 404 JSON response."""
    response = client.get("/api/non-existent-endpoint", headers={"Accept": "application/json"})
    assert response.status_code == 404
    json_data = response.get_json()
    assert json_data is not None
    assert json_data["error"] == "Not Found"
    assert json_data["status_code"] == 404


def test_500_error_handling_json(client, app):
    """Test that a 500 internal server error returns JSON for API requests."""
    app.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.get("/error-trigger", headers={"Accept": "application/json"})
    assert response.status_code == 500
    json_data = response.get_json()
    assert json_data is not None
    assert json_data["error"] == "Internal Server Error"
    assert json_data["status_code"] == 500


def test_500_error_handling_html(client, app):
    """Test that a 500 internal server error returns HTML page for browser requests."""
    app.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.get("/error-trigger", headers={"Accept": "text/html"})
    assert response.status_code == 500
    assert b"Internal Server Error" in response.data
    assert b"500" in response.data


def test_error_trigger_forbidden_when_not_debug(client, app):
    """Test that /error-trigger is forbidden when debug and testing are disabled."""
    app.config["TESTING"] = False
    app.config["DEBUG"] = False
    response = client.get("/error-trigger")
    assert response.status_code == 403
    json_data = response.get_json()
    assert json_data["error"] == "Forbidden"


def test_security_headers_present(client):
    """Test that security headers are injected into HTTP responses."""
    response = client.get("/")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"


def test_api_system_metrics(client):
    """Test /api/system-metrics endpoint returns actual metrics."""
    response = client.get("/api/system-metrics")
    assert response.status_code == 200
    data = response.get_json()
    assert "system" in data
    assert "aws" in data
    assert "docker" in data
    assert "uptime_seconds" in data
    assert "disk_total_gb" in data["system"]


def test_api_monitoring(client):
    """Test /api/monitoring endpoint returns consolidated metrics."""
    response = client.get("/api/monitoring")
    assert response.status_code == 200
    data = response.get_json()
    assert "system" in data
    assert "docker" in data
    assert "hosting" in data
    assert "uptime_seconds" in data
    assert data["status"] == "healthy"


def test_api_alerts_endpoint(client):
    """Test /api/alerts returns active alerts list."""
    response = client.get("/api/alerts")
    assert response.status_code == 200
    data = response.get_json()
    assert "alerts" in data
    assert "count" in data
    assert isinstance(data["alerts"], list)


def test_api_logs(client, app):
    """Test /api/logs endpoint returns recent in-memory logs and sanitizes secrets."""
    app.logger.info("Normal operational log entry")
    app.logger.warning(f"Contains secret: {app.config['SECRET_KEY']}")

    response = client.get("/api/logs")
    assert response.status_code == 200
    data = response.get_json()
    assert "logs" in data
    assert "count" in data
    assert isinstance(data["logs"], list)

    log_messages = [entry["message"] for entry in data["logs"]]
    assert not any(app.config["SECRET_KEY"] in m for m in log_messages)


def test_get_uptime_seconds_helper(app):
    """Test get_uptime_seconds calculation and fallback."""
    assert get_uptime_seconds(app) >= 0

    with patch.dict(app.config, {"START_TIME": None}):
        assert get_uptime_seconds(app) == 0


def test_is_running_in_docker_helper():
    """Test container detection helper under different filesystem and environment conditions."""
    # 1. DOCKER_CONTAINER environment variable
    with patch.dict(os.environ, {"DOCKER_CONTAINER": "true"}):
        assert is_running_in_docker() is True

    # 2. CONTAINER environment variable
    with patch.dict(os.environ, {"DOCKER_CONTAINER": "", "CONTAINER": "docker"}):
        assert is_running_in_docker() is True

    # 3. Marker files
    with patch.dict(os.environ, {"DOCKER_CONTAINER": "", "CONTAINER": ""}):
        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda p: p == "/etc/clouddeploy-container"
            assert is_running_in_docker() is True

        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda p: p == "/.dockerenv"
            assert is_running_in_docker() is True

        # 4. cgroup keyword detection
        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda p: p == "/proc/self/cgroup"
            with patch("builtins.open", mock_open(read_data="12:cpu:/docker/1234567890")):
                assert is_running_in_docker() is True

        # 5. mountinfo overlay keyword detection
        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda p: p == "/proc/self/mountinfo"
            with patch("builtins.open", mock_open(read_data="50 1 0:40 / / rw,relatime - overlay overlay rw")):
                assert is_running_in_docker() is True

        # 6. Fallback when not in container
        with patch("os.path.exists", return_value=False):
            assert is_running_in_docker() is False

        # 7. Error handling
        with patch("os.path.exists", side_effect=PermissionError("Mocked access error")):
            assert is_running_in_docker() is False

        # 8. Open error handling on cgroup and mountinfo
        with patch("os.path.exists", side_effect=lambda p: p in ("/proc/self/cgroup", "/proc/self/mountinfo")):
            with patch("builtins.open", side_effect=PermissionError("Mocked file read error")):
                assert is_running_in_docker() is False


def test_get_runtime_privilege_helper():
    """Test get_runtime_privilege under various UIDs and host execution."""
    # Test UID 10001 (clouddeploy non-root)
    with patch("os.getuid", return_value=10001, create=True):
        priv = get_runtime_privilege()
        assert priv["is_non_root"] is True
        assert priv["uid"] == 10001
        assert "UID 10001" in priv["label"]

    # Test UID 0 (root warning)
    with patch("os.getuid", return_value=0, create=True):
        priv_root = get_runtime_privilege()
        assert priv_root["is_non_root"] is False
        assert priv_root["uid"] == 0
        assert "Root User" in priv_root["label"]

    # Test arbitrary non-root UID
    with patch("os.getuid", return_value=1000, create=True):
        priv_other = get_runtime_privilege()
        assert priv_other["is_non_root"] is True
        assert priv_other["uid"] == 1000

    # Test system without getuid (e.g. Windows)
    with patch.dict(os.environ, {"USERNAME": "testdev"}):
        with patch("os.getuid", side_effect=AttributeError("No getuid on Windows"), create=True):
            priv_win = get_runtime_privilege()
            assert priv_win["is_non_root"] is True
            assert priv_win["uid"] is None


def test_get_container_resource_limits_cgroup_v2():
    """Test container cgroup v2 resource limits inspection."""
    def fake_exists(path):
        return path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/cpu.max")

    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/memory.max":
            return mock_open(read_data="536870912\n")()  # 512 MB
        elif path == "/sys/fs/cgroup/memory.current":
            return mock_open(read_data="104857600\n")()  # 100 MB
        elif path == "/sys/fs/cgroup/cpu.max":
            return mock_open(read_data="10000 100000\n")()  # 0.1 vCPU
        return mock_open(read_data="")()

    with patch("os.path.exists", side_effect=fake_exists):
        with patch("builtins.open", side_effect=fake_open):
            limits = get_container_resource_limits()
            assert limits["cgroup_version"] == "v2"
            assert limits["container_memory_limit_mb"] == 512.0
            assert limits["container_memory_usage_mb"] == 100.0
            assert limits["container_cpu_limit_cores"] == 0.1


def test_get_container_resource_limits_cgroup_v1():
    """Test container cgroup v1 resource limits inspection."""
    def fake_exists(path):
        return path in (
            "/sys/fs/cgroup/memory/memory.limit_in_bytes",
            "/sys/fs/cgroup/memory/memory.usage_in_bytes",
            "/sys/fs/cgroup/cpu/cpu.cfs_quota_us",
            "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
        )

    def fake_open(path, *args, **kwargs):
        if path == "/sys/fs/cgroup/memory/memory.limit_in_bytes":
            return mock_open(read_data="268435456\n")()  # 256 MB
        elif path == "/sys/fs/cgroup/memory/memory.usage_in_bytes":
            return mock_open(read_data="52428800\n")()  # 50 MB
        elif path == "/sys/fs/cgroup/cpu/cpu.cfs_quota_us":
            return mock_open(read_data="50000\n")()
        elif path == "/sys/fs/cgroup/cpu/cpu.cfs_period_us":
            return mock_open(read_data="100000\n")()  # 0.5 vCPU
        return mock_open(read_data="")()

    with patch("os.path.exists", side_effect=fake_exists):
        with patch("builtins.open", side_effect=fake_open):
            limits = get_container_resource_limits()
            assert limits["cgroup_version"] == "v1"
            assert limits["container_memory_limit_mb"] == 256.0
            assert limits["container_cpu_limit_cores"] == 0.5


def test_get_system_metrics_disk_and_mem():
    """Test get_system_metrics with mocked /proc/meminfo and disk failure."""
    meminfo_content = (
        "MemTotal:        16384000 kB\n"
        "MemFree:          8192000 kB\n"
        "MemAvailable:    12288000 kB\n"
    )
    with patch("os.path.exists") as mock_exists:
        mock_exists.side_effect = lambda p: p == "/proc/meminfo"
        with patch("builtins.open", mock_open(read_data=meminfo_content)):
            metrics = get_system_metrics()
            assert "host_node" in metrics
            assert metrics["host_node"]["physical_ram"] != "unavailable"
            assert "MB" in metrics["host_node"]["physical_ram"]

    with patch("shutil.disk_usage", side_effect=OSError("Disk error")):
        with patch("os.path.exists", return_value=False):
            metrics = get_system_metrics()
            assert metrics["disk_total_gb"] == 0
            assert metrics["disk_used_pct"] == 0


def test_get_aws_cloud_status_connected():
    """Test get_aws_cloud_status when IMDSv2 succeeds."""
    mock_token_resp = MagicMock()
    mock_token_resp.read.return_value = b"token-123"
    mock_token_resp.__enter__.return_value = mock_token_resp

    mock_id_resp = MagicMock()
    mock_id_resp.read.return_value = b"i-0123456789abcdef0"
    mock_id_resp.__enter__.return_value = mock_id_resp

    with patch("urllib.request.urlopen", side_effect=[mock_token_resp, mock_id_resp]):
        status = get_aws_cloud_status()
        assert status["connected"] is True
        assert status["instance_id"] == "i-0123456789abcdef0"


def test_get_aws_cloud_status_unconnected():
    """Test get_aws_cloud_status when IMDSv2 fails (local environment)."""
    with patch("urllib.request.urlopen", side_effect=OSError("IMDS timeout")):
        status = get_aws_cloud_status()
        assert status["connected"] is False
        assert "Optional Extension" in status["status"]


def test_parse_duration_seconds():
    """Test parse_duration_seconds helper."""
    d = parse_duration_seconds("2026-11-12T10:00:00Z", "2026-11-12T10:01:30Z")
    assert d == 90
    assert parse_duration_seconds(None, None) is None
    assert parse_duration_seconds("invalid", "invalid") is None


def test_fetch_github_workflows_success():
    """Test fetch_github_workflows when GitHub API returns valid runs."""
    sample_payload = {
        "total_count": 1,
        "workflow_runs": [{
            "id": 9999,
            "name": "CI Pipeline",
            "head_branch": "main",
            "head_sha": "1234567890abcdef",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-11-12T10:00:00Z",
            "updated_at": "2026-11-12T10:02:00Z",
            "html_url": "https://github.com/test/run/9999",
            "event": "push"
        }]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(sample_payload).encode("utf-8")
    mock_resp.headers = {"X-RateLimit-Remaining": "58"}
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = fetch_github_workflows("ullas-reddy-g/CloudDeploy-AWS-CICD", token="fake-token", force_refresh=True)
        assert res["integration_status"] == "connected"
        assert len(res["workflow_runs"]) == 1
        assert res["workflow_runs"][0]["duration_seconds"] == 120
        assert res["workflow_runs"][0]["commit_sha"] == "12345678"

        # Verify caching returns identical result without HTTP call
        cached_res = fetch_github_workflows("ullas-reddy-g/CloudDeploy-AWS-CICD", force_refresh=False)
        assert cached_res["integration_status"] == "connected"


def test_fetch_github_workflows_errors():
    """Test fetch_github_workflows under 403, 404, 500, and network error."""
    import app.routes
    app.routes._github_cache["data"] = None

    # Test 403 Rate Limit
    err_403 = urllib.error.HTTPError("https://api.github.com", 403, "Rate Limit", {"X-RateLimit-Remaining": "0"}, None)
    with patch("urllib.request.urlopen", side_effect=err_403):
        res = fetch_github_workflows("ullas-reddy-g/CloudDeploy-AWS-CICD", force_refresh=True)
        assert res["integration_status"] == "rate_limited"

    # Test 404 Not Found
    err_404 = urllib.error.HTTPError("https://api.github.com", 404, "Not Found", {}, None)
    with patch("urllib.request.urlopen", side_effect=err_404):
        res = fetch_github_workflows("unknown/repo", force_refresh=True)
        assert res["integration_status"] == "not_found"

    # Test 500 Internal Error
    err_500 = urllib.error.HTTPError("https://api.github.com", 500, "Server Error", {}, None)
    with patch("urllib.request.urlopen", side_effect=err_500):
        res = fetch_github_workflows("unknown/repo", force_refresh=True)
        assert res["integration_status"] == "error"

    # Test URLError
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network unreachable")):
        res = fetch_github_workflows("unknown/repo", force_refresh=True)
        assert res["integration_status"] == "unavailable"


def test_api_github_workflows_endpoint(client):
    """Test /api/github/workflows endpoint."""
    with patch("app.routes.fetch_github_workflows") as mock_fetch:
        mock_fetch.return_value = {
            "integration_status": "connected",
            "workflow_runs": [],
            "total_count": 0
        }
        response = client.get("/api/github/workflows?refresh=true")
        assert response.status_code == 200
        data = response.get_json()
        assert data["integration_status"] == "connected"


def test_fetch_render_deployments(app):
    """Test fetch_render_deployments with and without credentials."""
    with app.app_context():
        # Unconfigured
        unconf = fetch_render_deployments("", "", force_refresh=True)
        assert unconf["integration_status"] == "unconfigured"
        assert unconf["provider"] == "Render (Cloud PaaS)"
        assert unconf["record_type"] == "Application Runtime Metadata"

        # Connected
        sample_deploys = [{
            "deploy": {
                "id": "dep-1234",
                "status": "live",
                "commit": {"id": "abcdef123456", "message": "Deploy commit"},
                "createdAt": "2026-11-12T10:00:00Z",
                "updatedAt": "2026-11-12T10:05:00Z",
                "finishedAt": "2026-11-12T10:05:00Z"
            }
        }]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(sample_deploys).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            conn = fetch_render_deployments("srv-123", "rnd_testkey", force_refresh=True)
            assert conn["integration_status"] == "connected"
            assert len(conn["deployments"]) == 1
            assert conn["deployments"][0]["commit_id"] == "abcdef12"

            # Cache hit test
            cached_conn = fetch_render_deployments("srv-123", "rnd_testkey", force_refresh=False)
            assert cached_conn["integration_status"] == "connected"

        # Error
        with patch("urllib.request.urlopen", side_effect=OSError("Render API unreachable")):
            err_res = fetch_render_deployments("srv-123", "rnd_testkey", force_refresh=True)
            assert err_res["integration_status"] == "error"


def test_api_deployments_endpoint(client):
    """Test /api/deployments endpoint."""
    response = client.get("/api/deployments")
    assert response.status_code == 200
    data = response.get_json()
    assert "integration_status" in data
    assert "deployments" in data


def test_get_cicd_pipeline_status():
    """Test get_cicd_pipeline_status using mock fetch_github_workflows."""
    with patch("app.routes.fetch_github_workflows") as mock_fetch:
        mock_fetch.return_value = {
            "workflow_runs": [{
                "name": "CI Pipeline",
                "conclusion": "success",
                "status": "completed",
                "commit_sha": "abc12345",
                "html_url": "https://github.com/test",
                "updated_at": "2026-11-12T10:00:00Z"
            }]
        }
        res = get_cicd_pipeline_status("test/repo")
        assert res["available"] is True
        assert res["conclusion"] == "success"

        mock_fetch.return_value = {"workflow_runs": []}
        res_empty = get_cicd_pipeline_status("test/repo")
        assert res_empty["available"] is False


def test_get_deployment_history_file(app):
    """Test reading deployment history from a JSON file."""
    mock_data = json.dumps([{
        "deployment_id": "sha-test-1",
        "version": "1.0.1",
        "timestamp": "2026-11-08 10:00:00 UTC",
        "environment": "production",
        "status": "SUCCESS"
    }])
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with app.app_context():
                history = get_deployment_history()
                assert len(history) == 1
                assert history[0]["deployment_id"] == "sha-test-1"


def test_get_deployment_history_corrupted_fallback(app):
    """Test fallback when deployment history file contains invalid JSON."""
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data="{invalid-json")):
            with app.app_context():
                history = get_deployment_history()
                assert len(history) == 1
                assert history[0]["status"] == "LIVE"


def test_disk_alert_rendered_in_dashboard(client):
    """Test that a high disk utilization alert is rendered when disk exceeds 85%."""
    mock_metrics = {
        "disk_total_gb": 100.0,
        "disk_used_gb": 90.0,
        "disk_free_gb": 10.0,
        "disk_used_pct": 90.0,
        "cpu_count": 4,
        "mem_total": "unavailable",
        "mem_available": "unavailable",
        "mem_used_pct": "unavailable",
        "container": {
            "memory_limit": "Metric unavailable in current hosting environment",
            "memory_usage": "Metric unavailable in current hosting environment",
            "cpu_allocation": "Shared Host Allocation",
            "cgroup_version": "unavailable",
        },
        "host_node": {
            "label": "Underlying Host Node Capacity",
            "cpu_cores": "4 vCPU",
            "physical_ram": "16384 MB",
            "disk_total_gb": 100.0,
            "disk_used_gb": 90.0,
            "disk_free_gb": 10.0,
            "disk_used_pct": 90.0,
            "disk_scope": "Host Root Filesystem",
        }
    }
    with patch("app.routes.get_system_metrics", return_value=mock_metrics):
        response = client.get("/deployment")
        assert response.status_code == 200
        assert b"High Storage Capacity Alert" in response.data


def test_get_active_alerts_variations(app):
    """Test alert evaluation with CI failure."""
    system_metrics = {"disk_used_pct": 50.0}
    cicd_info = {"conclusion": "failure", "commit_sha": "fail1234"}
    aws_info = {"connected": False}
    alerts = get_active_alerts(app, system_metrics, cicd_info, aws_info)
    assert any(a["type"] == "danger" and "CI/CD Pipeline Failure" in a["title"] for a in alerts)


def test_recent_logs_handler_error_handling(app):
    """Test error handling in RecentLogsHandler when emit encounters an error."""
    handler = app.log_buffer
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None
    )
    with patch.object(record, "getMessage", side_effect=Exception("Formatting failed")):
        handler.emit(record)


def test_create_app_env_overrides():
    """Test create_app dynamic environment variable overrides."""
    env_vars = {
        "APP_VERSION": "2.5.0-override",
        "DEPLOYMENT_ID": "deploy-override-99",
        "RENDER_GIT_COMMIT": "abcdef123456789",
        "HOSTING_PROVIDER": "render",
        "RENDER_SERVICE_ID": "srv-test-99",
        "RENDER_EXTERNAL_URL": "https://test.onrender.com",
        "AWS_REGION": "eu-west-1",
        "DOCKER_CONTAINER": "true",
        "GITHUB_REPOSITORY": "ullas-reddy-g/CloudDeploy-AWS-CICD",
    }
    with patch.dict(os.environ, env_vars):
        custom_app = create_app("testing")
        assert custom_app.config["APP_VERSION"] == "2.5.0-override"
        assert custom_app.config["DEPLOYMENT_ID"] == "abcdef12"
        assert custom_app.config["HOSTING_PROVIDER"] == "render"
        assert custom_app.config["RENDER_SERVICE_ID"] == "srv-test-99"
        assert custom_app.config["RENDER_EXTERNAL_URL"] == "https://test.onrender.com"
        assert custom_app.config["AWS_REGION"] == "eu-west-1"
        assert custom_app.config["DOCKER_CONTAINER"] is True
        assert custom_app.config["GITHUB_REPOSITORY"] == "ullas-reddy-g/CloudDeploy-AWS-CICD"


def test_get_system_metrics_meminfo_exception():
    """Test get_system_metrics when opening /proc/meminfo raises an exception."""
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", side_effect=PermissionError("meminfo locked")):
            metrics = get_system_metrics()
            assert metrics["host_node"]["physical_ram"] == "unavailable"


def test_fetch_github_workflows_fallback_with_existing_cache():
    """Test GitHub API fallback to cached telemetry when errors occur."""
    import app.routes
    app.routes._github_cache["data"] = {
        "integration_status": "connected",
        "workflow_runs": [{"id": 1}],
        "repository": "test/repo"
    }
    app.routes._github_cache["timestamp"] = 0.0

    # Test HTTP error with cache fallback
    err = urllib.error.HTTPError("https://api.github.com", 500, "Server Error", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        res = fetch_github_workflows("test/repo", force_refresh=True)
        assert res["cached"] is True
        assert "warning" in res

    # Test generic exception with cache fallback
    with patch("urllib.request.urlopen", side_effect=RuntimeError("Connection timeout")):
        res = fetch_github_workflows("test/repo", force_refresh=True)
        assert res["cached"] is True
        assert "warning" in res


def test_create_app_default_config():
    """Test create_app when config_name is None defaults to production environment."""
    with patch.dict(os.environ, {}, clear=True):
        default_app = create_app(None)
        assert default_app.config["ENVIRONMENT"] == "production"
