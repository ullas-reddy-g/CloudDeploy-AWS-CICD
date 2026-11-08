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


def test_500_error_handling(client, app):
    """Test that a 500 internal server error is caught and formatted properly."""
    app.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.get("/error-trigger", headers={"Accept": "application/json"})
    assert response.status_code == 500
    json_data = response.get_json()
    assert json_data is not None
    assert json_data["error"] == "Internal Server Error"
    assert json_data["status_code"] == 500


def test_security_headers_present(client):
    """Test that security headers are injected into HTTP responses."""
    response = client.get("/")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
