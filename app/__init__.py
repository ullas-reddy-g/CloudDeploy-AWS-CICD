import logging
import os
import sys
from collections import deque
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request
from app.config import config_by_name


class RecentLogsHandler(logging.Handler):
    """Ring-buffer logging handler retaining recent application logs for monitoring."""
    def __init__(self, capacity=50):
        super().__init__()
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        try:
            self.buffer.append({
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "level": record.levelname,
                "message": record.getMessage(),
            })
        except Exception:
            self.handleError(record)


def setup_logging(app):
    """Configure structured logging for stdout (CloudWatch compatible) and in-memory buffer."""
    log_level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [CloudDeploy] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %z"
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(log_level)

    recent_logs_handler = RecentLogsHandler(capacity=50)
    recent_logs_handler.setFormatter(formatter)
    recent_logs_handler.setLevel(log_level)

    app.logger.handlers.clear()
    app.logger.addHandler(stdout_handler)
    app.logger.addHandler(recent_logs_handler)
    app.logger.setLevel(log_level)

    app.log_buffer = recent_logs_handler


def create_app(config_name=None):
    """Application factory for CloudDeploy Flask application."""
    if config_name is None:
        config_name = os.getenv("ENVIRONMENT", "production")

    app = Flask(__name__)
    selected_config = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(selected_config)

    # Ensure dynamic override from environment variables if present
    if os.getenv("APP_VERSION"):
        app.config["APP_VERSION"] = os.getenv("APP_VERSION")
    if os.getenv("DEPLOYMENT_ID"):
        app.config["DEPLOYMENT_ID"] = os.getenv("DEPLOYMENT_ID")
    if os.getenv("AWS_REGION"):
        app.config["AWS_REGION"] = os.getenv("AWS_REGION")
    if os.getenv("GITHUB_REPOSITORY"):
        app.config["GITHUB_REPOSITORY"] = os.getenv("GITHUB_REPOSITORY")

    setup_logging(app)

    # Register blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # Register error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.warning(f"404 Not Found: {request.path}")
        if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
            return jsonify({
                "error": "Not Found",
                "message": "The requested resource could not be found on this server.",
                "status_code": 404,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }), 404
        return render_template("404.html", path=request.path), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"500 Internal Server Error: {str(error)}", exc_info=True)
        if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
            return jsonify({
                "error": "Internal Server Error",
                "message": "An internal server error occurred.",
                "status_code": 500,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }), 500
        return render_template("500.html"), 500

    @app.after_request
    def add_security_headers(response):
        """Add basic HTTP security headers."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    app.logger.info(
        f"CloudDeploy initialized: {app.config['APP_NAME']} v{app.config['APP_VERSION']} "
        f"[{app.config['ENVIRONMENT']}]"
    )

    return app
