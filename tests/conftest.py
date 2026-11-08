import pytest
from app import create_app


@pytest.fixture
def app():
    """Create and configure a testing Flask application instance."""
    app_instance = create_app("testing")
    app_instance.config.update({
        "TESTING": True,
        "DEBUG": True,
        "APP_NAME": "CloudDeploy-Test",
        "APP_VERSION": "1.0.0-test",
        "ENVIRONMENT": "testing",
        "DEPLOYMENT_ID": "test-ci-build-1",
        "AWS_REGION": "us-east-1",
    })
    yield app_instance


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()
