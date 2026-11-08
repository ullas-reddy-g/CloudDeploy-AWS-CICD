import json
import logging
import os
from unittest.mock import patch, mock_open, MagicMock
from app import create_app
from app.routes import (
    get_uptime_seconds,
    is_running_in_docker,
    get_system_metrics,
    get_aws_cloud_status,
    get_cicd_pipeline_status,
    get_deployment_history,
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


def test_api_logs(client):
    """Test /api/logs endpoint returns recent in-memory logs."""
    response = client.get("/api/logs")
    assert response.status_code == 200
    data = response.get_json()
    assert "logs" in data
    assert "count" in data
    assert isinstance(data["logs"], list)


def test_get_uptime_seconds_helper(app):
    """Test get_uptime_seconds calculation and fallback."""
    assert get_uptime_seconds(app) >= 0

    with patch.dict(app.config, {"START_TIME": None}):
        assert get_uptime_seconds(app) == 0


def test_is_running_in_docker_helper():
    """Test container detection helper under different filesystem conditions."""
    with patch("os.path.exists") as mock_exists:
        mock_exists.side_effect = lambda p: p == "/.dockerenv"
        assert is_running_in_docker() is True

    with patch("os.path.exists") as mock_exists:
        mock_exists.side_effect = lambda p: p == "/proc/self/cgroup"
        with patch("builtins.open", mock_open(read_data="12:cpu:/docker/1234567890")):
            assert is_running_in_docker() is True

    with patch("os.path.exists") as mock_exists:
        mock_exists.side_effect = lambda p: p == "/proc/self/cgroup"
        with patch("builtins.open", mock_open(read_data="12:cpu:/system.slice/init.scope")):
            assert is_running_in_docker() is False

    with patch("os.path.exists", return_value=False):
        assert is_running_in_docker() is False

    with patch("os.path.exists", side_effect=PermissionError("Mocked access error")):
        assert is_running_in_docker() is False


def test_get_system_metrics_fallback():
    """Test get_system_metrics fallback on error."""
    with patch("shutil.disk_usage", side_effect=OSError("Disk error")):
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
        assert "Awaiting AWS Connection" in status["status"]


def test_get_cicd_pipeline_status_connected():
    """Test get_cicd_pipeline_status when GitHub API returns runs."""
    sample_payload = {
        "workflow_runs": [{
            "id": 987654321,
            "name": "CI Pipeline - Build & Test",
            "conclusion": "success",
            "status": "completed",
            "head_sha": "abc1234567890",
            "html_url": "https://github.com/ullas-reddy-g/CloudDeploy-AWS-CICD/actions/runs/987654321",
            "updated_at": "2026-11-08T12:00:00Z"
        }]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(sample_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = get_cicd_pipeline_status("ullas-reddy-g/CloudDeploy-AWS-CICD")
        assert res["available"] is True
        assert res["conclusion"] == "success"
        assert res["commit_sha"] == "abc12345"


def test_get_cicd_pipeline_status_fallback():
    """Test get_cicd_pipeline_status fallback when GitHub API fails or repository is unpublished."""
    with patch("urllib.request.urlopen", side_effect=OSError("API rate limit / offline")):
        res = get_cicd_pipeline_status("ullas-reddy-g/CloudDeploy-AWS-CICD")
        assert res["available"] is False
        assert "Awaiting GitHub" in res["status"]


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
                assert history[0]["status"] == "SUCCESS"


def test_disk_alert_rendered_in_dashboard(client):
    """Test that a high disk utilization alert is rendered when disk exceeds 85%."""
    mock_metrics = {
        "disk_total_gb": 100.0,
        "disk_used_gb": 90.0,
        "disk_free_gb": 10.0,
        "disk_used_pct": 90.0,
        "cpu_count": 4,
    }
    with patch("app.routes.get_system_metrics", return_value=mock_metrics):
        response = client.get("/deployment")
        assert response.status_code == 200
        assert b"High Disk Utilization Alert" in response.data


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
        "AWS_REGION": "eu-west-1",
        "GITHUB_REPOSITORY": "ullas-reddy-g/CloudDeploy-AWS-CICD",
    }
    with patch.dict(os.environ, env_vars):
        custom_app = create_app("testing")
        assert custom_app.config["APP_VERSION"] == "2.5.0-override"
        assert custom_app.config["DEPLOYMENT_ID"] == "deploy-override-99"
        assert custom_app.config["AWS_REGION"] == "eu-west-1"
        assert custom_app.config["GITHUB_REPOSITORY"] == "ullas-reddy-g/CloudDeploy-AWS-CICD"


def test_create_app_default_config():
    """Test create_app when config_name is None defaults to production environment."""
    with patch.dict(os.environ, {}, clear=True):
        default_app = create_app(None)
        assert default_app.config["ENVIRONMENT"] == "production"
