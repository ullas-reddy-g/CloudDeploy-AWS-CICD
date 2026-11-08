import os
import platform
import sys
from datetime import datetime, timezone
from flask import Blueprint, render_template, jsonify, current_app

main_bp = Blueprint("main", __name__)


def get_uptime_seconds(app):
    start_time = app.config.get("START_TIME")
    if not start_time:
        return 0
    now = datetime.now(timezone.utc)
    return int((now - start_time).total_seconds())


def is_running_in_docker():
    """Detect safely whether the application is running inside a Docker container."""
    try:
        if os.path.exists("/.dockerenv"):
            return True
        cgroup_path = "/proc/self/cgroup"
        if os.path.exists(cgroup_path):
            with open(cgroup_path, "r", encoding="utf-8") as f:
                content = f.read()
                if "docker" in content or "kubepods" in content or "containerd" in content:
                    return True
    except Exception:
        pass
    return False


@main_bp.route("/")
def index():
    """Render the primary CloudDeploy home dashboard."""
    app_info = {
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "aws_region": current_app.config["AWS_REGION"],
        "is_container": is_running_in_docker(),
        "uptime_seconds": get_uptime_seconds(current_app),
        "os_platform": f"{platform.system()} {platform.release()}",
        "python_version": sys.version.split()[0],
    }
    return render_template("index.html", info=app_info)


@main_bp.route("/deployment")
def deployment():
    """Render the deployment status and cloud infrastructure diagnostics page."""
    deployment_info = {
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "aws_region": current_app.config["AWS_REGION"],
        "is_container": is_running_in_docker(),
        "uptime_seconds": get_uptime_seconds(current_app),
        "start_time": current_app.config["START_TIME"].strftime("%Y-%m-%d %H:%M:%S UTC"),
        "hostname": platform.node(),
    }
    return render_template("dashboard.html", info=deployment_info)


@main_bp.route("/about")
def about():
    """Render the project architecture and pipeline overview page."""
    return render_template("about.html")


@main_bp.route("/health")
def health():
    """
    Health check endpoint for container probes, load balancers, and monitoring.
    Returns HTTP 200 with JSON payload.
    """
    current_time_iso = datetime.now(timezone.utc).isoformat()
    return jsonify({
        "status": "healthy",
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "timestamp": current_time_iso
    }), 200


@main_bp.route("/api/info")
def api_info():
    """
    Public non-sensitive application metadata endpoint.
    Guaranteed not to leak AWS secrets, credentials, or internal networks.
    """
    return jsonify({
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "is_container": is_running_in_docker(),
        "uptime_seconds": get_uptime_seconds(current_app),
        "python_version": sys.version.split()[0],
        "status": "operational"
    }), 200


@main_bp.route("/error-trigger")
def trigger_error():
    """Route used strictly for testing the 500 error handler."""
    if current_app.config.get("TESTING") or current_app.config.get("DEBUG"):
        raise RuntimeError("Intentional error for testing 500 error handler")
    return jsonify({"error": "Forbidden"}), 403
