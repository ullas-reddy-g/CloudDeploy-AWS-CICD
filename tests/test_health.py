from datetime import datetime


def test_health_endpoint_status(client):
    """Test that the /health endpoint returns HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint_payload(client):
    """Test that /health returns required JSON keys with valid values."""
    response = client.get("/health")
    data = response.get_json()
    assert data is not None
    assert data.get("status") == "healthy"
    assert data.get("app_name") == "CloudDeploy-Test"
    assert data.get("version") == "1.0.0-test"
    assert "timestamp" in data

    # Verify timestamp format (ISO 8601)
    timestamp_str = data["timestamp"]
    parsed_dt = datetime.fromisoformat(timestamp_str)
    assert parsed_dt is not None


def test_api_info_endpoint(client):
    """Test that /api/info returns expected non-sensitive fields."""
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data.get("app_name") == "CloudDeploy-Test"
    assert data.get("version") == "1.0.0-test"
    assert data.get("environment") == "testing"
    assert data.get("deployment_id") == "test-ci-build-1"
    assert data.get("status") == "operational"
    assert "python_version" in data

    # Verify no sensitive information leaked
    assert "SECRET_KEY" not in data
    assert "AWS_ACCESS_KEY_ID" not in data
    assert "AWS_SECRET_ACCESS_KEY" not in data
