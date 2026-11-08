import json
import os
import platform
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from flask import Blueprint, render_template, jsonify, current_app

main_bp = Blueprint("main", __name__)


def get_uptime_seconds(app):
    """Calculate running uptime in seconds."""
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


def get_system_metrics():
    """Retrieve actual host/system storage and CPU hardware metrics."""
    try:
        disk = shutil.disk_usage(os.getcwd())
        total_gb = round(disk.total / (1024 ** 3), 1)
        used_gb = round(disk.used / (1024 ** 3), 1)
        free_gb = round(disk.free / (1024 ** 3), 1)
        used_pct = round((disk.used / disk.total) * 100, 1)
    except Exception:
        total_gb, used_gb, free_gb, used_pct = 0, 0, 0, 0

    cpu_count = os.cpu_count() or 1
    return {
        "disk_total_gb": total_gb,
        "disk_used_gb": used_gb,
        "disk_free_gb": free_gb,
        "disk_used_pct": used_pct,
        "cpu_count": cpu_count,
    }


def get_aws_cloud_status():
    """
    Attempt to fetch real EC2 metadata via IMDSv2 with a strict 0.5s timeout.
    Returns honest status if running locally or unconfigured.
    """
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            method="PUT"
        )
        with urllib.request.urlopen(token_req, timeout=0.5) as resp:
            token = resp.read().decode("utf-8")

        id_req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token}
        )
        with urllib.request.urlopen(id_req, timeout=0.5) as resp:
            instance_id = resp.read().decode("utf-8")

        return {
            "status": "Connected (AWS EC2)",
            "instance_id": instance_id,
            "connected": True,
            "cloudwatch_agent": "Installed & Active via User Data",
        }
    except Exception:
        return {
            "status": "Awaiting AWS Connection",
            "instance_id": "Unavailable (Not hosted on EC2)",
            "connected": False,
            "cloudwatch_agent": "Not Configured (Requires AWS Host)",
        }


def get_cicd_pipeline_status(repo_name):
    """
    Attempt to fetch latest GitHub Actions workflow run via GitHub API with a 1s timeout.
    Returns actual workflow information or honest unconfigured status.
    """
    try:
        url = f"https://api.github.com/repos/{repo_name}/actions/runs?per_page=1"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CloudDeploy-Monitor", "Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            runs = data.get("workflow_runs", [])
            if runs:
                latest = runs[0]
                return {
                    "status": "Connected",
                    "workflow_name": latest.get("name", "CI/CD"),
                    "conclusion": latest.get("conclusion") or "in_progress",
                    "status_code": latest.get("status", "completed"),
                    "commit_sha": latest.get("head_sha", "")[:8],
                    "html_url": latest.get("html_url", ""),
                    "updated_at": latest.get("updated_at", ""),
                    "available": True,
                }
    except Exception:
        pass
    return {
        "status": "Awaiting GitHub Repository Publication",
        "workflow_name": "CI/CD Pipeline",
        "conclusion": "pending_publication",
        "status_code": "unconfigured",
        "commit_sha": "Unavailable",
        "html_url": f"https://github.com/{repo_name}/actions",
        "updated_at": "Pending first push",
        "available": False,
    }


def get_deployment_history():
    """
    Retrieve real deployment history records from /opt/clouddeploy/deployment_history.json
    or fallback to current deployment record if history file has not yet accumulated entries.
    """
    history_paths = [
        "/opt/clouddeploy/deployment_history.json",
        os.path.join(os.getcwd(), "deployment_history.json")
    ]
    for path in history_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                    if isinstance(records, list) and records:
                        return records
            except Exception:
                pass

    # Default to current active deployment entry
    return [{
        "deployment_id": current_app.config.get("DEPLOYMENT_ID", "local-build"),
        "version": current_app.config.get("APP_VERSION", "1.0.0"),
        "timestamp": current_app.config.get("START_TIME").strftime("%Y-%m-%d %H:%M:%S UTC"),
        "environment": current_app.config.get("ENVIRONMENT", "production"),
        "status": "SUCCESS",
        "details": "Active application runtime",
    }]


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
    """Render the comprehensive CloudDeploy Monitoring & Diagnostics Dashboard."""
    repo = current_app.config.get("GITHUB_REPOSITORY", "ullas-reddy-g/CloudDeploy-AWS-CICD")
    is_docker = is_running_in_docker()

    system_metrics = get_system_metrics()
    aws_info = get_aws_cloud_status()
    cicd_info = get_cicd_pipeline_status(repo)
    deploy_history = get_deployment_history()

    # Dynamic alerts evaluation
    alerts = []
    if system_metrics["disk_used_pct"] > 85:
        alerts.append({
            "type": "warning",
            "title": "High Disk Utilization Alert",
            "message": f"Host disk space is at {system_metrics['disk_used_pct']}% utilization."
        })
    if not is_docker:
        alerts.append({
            "type": "info",
            "title": "Host Mode Active",
            "message": "Application is running directly on host Python runtime (Docker container inactive)."
        })
    if not aws_info["connected"]:
        alerts.append({
            "type": "secondary",
            "title": "AWS Cloud Disconnected",
            "message": "Local development host. AWS EC2 metadata and CloudWatch Agent unavailable."
        })

    dashboard_data = {
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "aws_region": current_app.config["AWS_REGION"],
        "is_container": is_docker,
        "container_status": "Running (Isolated UID 10001)" if is_docker else "Host Execution (Local)",
        "uptime_seconds": get_uptime_seconds(current_app),
        "start_time": current_app.config["START_TIME"].strftime("%Y-%m-%d %H:%M:%S UTC"),
        "hostname": platform.node(),
        "github_repo": repo,
        "system_metrics": system_metrics,
        "aws_cloud": aws_info,
        "cicd": cicd_info,
        "history": deploy_history,
        "alerts": alerts,
    }
    return render_template("dashboard.html", info=dashboard_data)


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


@main_bp.route("/api/system-metrics")
def api_system_metrics():
    """JSON endpoint providing actual host metrics and diagnostics."""
    return jsonify({
        "system": get_system_metrics(),
        "aws": get_aws_cloud_status(),
        "docker": {
            "is_container": is_running_in_docker(),
            "hostname": platform.node(),
        },
        "uptime_seconds": get_uptime_seconds(current_app),
    }), 200


@main_bp.route("/api/logs")
def api_logs():
    """JSON endpoint returning recent application logs from memory buffer."""
    buf = getattr(current_app, "log_buffer", None)
    logs = list(buf.buffer) if buf else []
    return jsonify({
        "logs": logs,
        "count": len(logs),
    }), 200


@main_bp.route("/error-trigger")
def trigger_error():
    """Route used strictly for testing the 500 error handler."""
    if current_app.config.get("TESTING") or current_app.config.get("DEBUG"):
        raise RuntimeError("Intentional error for testing 500 error handler")
    return jsonify({"error": "Forbidden"}), 403
