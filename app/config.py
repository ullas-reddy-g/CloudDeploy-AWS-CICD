import os
from datetime import datetime, timezone


class Config:
    """Base application configuration."""
    APP_NAME = os.getenv("APP_NAME", "CloudDeploy")
    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    SECRET_KEY = os.getenv("SECRET_KEY", "clouddeploy-default-insecure-key-change-in-prod")
    PORT = int(os.getenv("PORT", "8000"))
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    DEPLOYMENT_ID = os.getenv("RENDER_GIT_COMMIT", os.getenv("DEPLOYMENT_ID", "local-build"))
    GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "ullas-reddy-g/CloudDeploy-AWS-CICD")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    HOSTING_PROVIDER = os.getenv(
        "HOSTING_PROVIDER",
        "render" if (os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID")) else "local"
    )
    RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID", "")
    RENDER_API_KEY = os.getenv("RENDER_API_KEY", "")
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://clouddeploy-aws-cicd.onrender.com")
    START_TIME = datetime.now(timezone.utc)
    TESTING = False
    DEBUG = False


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    ENVIRONMENT = "development"


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    ENVIRONMENT = "production"


class TestingConfig(Config):
    """Testing environment configuration."""
    TESTING = True
    DEBUG = True
    ENVIRONMENT = "testing"
    SECRET_KEY = "testing-secret-key"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": ProductionConfig,
}
