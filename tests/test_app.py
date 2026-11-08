import os
from unittest.mock import patch, mock_open
from app import create_app
from app.routes import get_uptime_seconds, is_running_in_docker


def test_homepage_status_and_content(client):
    """Test that the homepage returns HTTP 200 and expected branding."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"CloudDeploy" in response.data
    assert b"Automated CI/CD Pipeline Workflow" in response.data


def test_deployment_page(client):
    """Test that the deployment diagnostics page returns HTTP 200."""
    response = client.get("/deployment")
    assert response.status_code == 200
    assert b"Deployment & Infrastructure Diagnostics" in response.data
    assert b"test-ci-build-1" in response.data


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


def test_get_uptime_seconds_helper(app):
    """Test get_uptime_seconds calculation and fallback."""
    assert get_uptime_seconds(app) >= 0

    with patch.dict(app.config, {"START_TIME": None}):
        assert get_uptime_seconds(app) == 0


def test_is_running_in_docker_helper():
    """Test container detection helper under different filesystem conditions."""
    # Condition 1: /.dockerenv exists
    with patch("os.path.exists") as mock_exists:
        mock_exists.side_effect = lambda p: p == "/.dockerenv"
        assert is_running_in_docker() is True

    # Condition 2: /proc/self/cgroup contains docker
    with patch("os.path.exists") as mock_exists:
        mock_exists.side_effect = lambda p: p == "/proc/self/cgroup"
        with patch("builtins.open", mock_open(read_data="12:cpu:/docker/1234567890")):
            assert is_running_in_docker() is True

    # Condition 3: /proc/self/cgroup exists but no container markers
    with patch("os.path.exists") as mock_exists:
        mock_exists.side_effect = lambda p: p == "/proc/self/cgroup"
        with patch("builtins.open", mock_open(read_data="12:cpu:/system.slice/init.scope")):
            assert is_running_in_docker() is False

    # Condition 4: Neither exists
    with patch("os.path.exists", return_value=False):
        assert is_running_in_docker() is False

    # Condition 5: Exception raised during read
    with patch("os.path.exists", side_effect=PermissionError("Mocked access error")):
        assert is_running_in_docker() is False


def test_create_app_env_overrides():
    """Test create_app dynamic environment variable overrides."""
    env_vars = {
        "APP_VERSION": "2.5.0-override",
        "DEPLOYMENT_ID": "deploy-override-99",
        "AWS_REGION": "eu-west-1",
    }
    with patch.dict(os.environ, env_vars):
        custom_app = create_app("testing")
        assert custom_app.config["APP_VERSION"] == "2.5.0-override"
        assert custom_app.config["DEPLOYMENT_ID"] == "deploy-override-99"
        assert custom_app.config["AWS_REGION"] == "eu-west-1"


def test_create_app_default_config():
    """Test create_app when config_name is None defaults to production environment."""
    with patch.dict(os.environ, {}, clear=True):
        default_app = create_app(None)
        assert default_app.config["ENVIRONMENT"] == "production"
