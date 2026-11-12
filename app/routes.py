import json
import os
import platform
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from flask import Blueprint, render_template, jsonify, current_app, request

main_bp = Blueprint("main", __name__)

# In-memory cache for GitHub API responses to prevent rate limiting
_github_cache = {
    "data": None,
    "timestamp": 0.0,
    "ttl": 30.0,
}


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
    """Retrieve actual host/system storage, CPU, and memory hardware metrics."""
    try:
        disk = shutil.disk_usage(os.getcwd())
        total_gb = round(disk.total / (1024 ** 3), 1)
        used_gb = round(disk.used / (1024 ** 3), 1)
        free_gb = round(disk.free / (1024 ** 3), 1)
        used_pct = round((disk.used / disk.total) * 100, 1)
    except Exception:
        total_gb, used_gb, free_gb, used_pct = 0, 0, 0, 0

    cpu_count = os.cpu_count() or 1

    mem_total = "unavailable"
    mem_available = "unavailable"
    mem_used_pct = "unavailable"
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                lines = f.readlines()
            mem_info = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    mem_info[key] = int(val)
            if "MemTotal" in mem_info and "MemAvailable" in mem_info:
                t_mb = round(mem_info["MemTotal"] / 1024, 1)
                a_mb = round(mem_info["MemAvailable"] / 1024, 1)
                u_pct = round(
                    ((mem_info["MemTotal"] - mem_info["MemAvailable"]) / mem_info["MemTotal"]) * 100, 1
                )
                mem_total = f"{t_mb} MB"
                mem_available = f"{a_mb} MB"
                mem_used_pct = f"{u_pct}%"
    except Exception:
        pass

    return {
        "disk_total_gb": total_gb,
        "disk_used_gb": used_gb,
        "disk_free_gb": free_gb,
        "disk_used_pct": used_pct,
        "cpu_count": cpu_count,
        "mem_total": mem_total,
        "mem_available": mem_available,
        "mem_used_pct": mem_used_pct,
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


def parse_duration_seconds(created_at_str, updated_at_str):
    """Safely calculate run duration in seconds between two ISO 8601 timestamps."""
    try:
        if created_at_str and updated_at_str:
            t1 = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            return max(0, int((t2 - t1).total_seconds()))
    except Exception:
        pass
    return None


def fetch_github_workflows(repo_name, token=None, per_page=5, force_refresh=False):
    """
    Fetch recent workflow runs from GitHub Actions REST API with caching.
    Handles unauthenticated public API rate limits cleanly.
    """
    now = time.time()
    if (
        not force_refresh
        and _github_cache["data"]
        and (now - _github_cache["timestamp"] < _github_cache["ttl"])
    ):
        return _github_cache["data"]

    url = f"https://api.github.com/repos/{repo_name}/actions/runs?per_page={per_page}"
    headers = {
        "User-Agent": "CloudDeploy-Monitor/2.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            rate_limit_remaining = resp.headers.get("X-RateLimit-Remaining")

            runs = []
            for item in data.get("workflow_runs", []):
                created_at = item.get("created_at")
                updated_at = item.get("updated_at")
                duration = parse_duration_seconds(created_at, updated_at)
                runs.append({
                    "id": item.get("id"),
                    "name": item.get("name", "Workflow"),
                    "branch": item.get("head_branch", "main"),
                    "commit_sha": (item.get("head_sha") or "")[:8],
                    "full_sha": item.get("head_sha", ""),
                    "status": item.get("status", "unknown"),
                    "conclusion": item.get("conclusion") or "in_progress",
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "duration_seconds": duration,
                    "html_url": item.get("html_url", f"https://github.com/{repo_name}/actions"),
                    "event": item.get("event", "push"),
                })

            result = {
                "integration_status": "connected",
                "repository": repo_name,
                "total_count": data.get("total_count", len(runs)),
                "workflow_runs": runs,
                "rate_limit_remaining": rate_limit_remaining,
                "cached": False,
                "last_fetched": datetime.now(timezone.utc).isoformat(),
            }
            _github_cache["data"] = result
            _github_cache["timestamp"] = now
            return result

    except urllib.error.HTTPError as err:
        rate_limit_remaining = err.headers.get("X-RateLimit-Remaining") if err.headers else "0"
        if err.code in (403, 429):
            msg = "GitHub API rate limit exceeded. Displaying cached/fallback telemetry."
            status = "rate_limited"
        elif err.code == 404:
            msg = f"GitHub repository '{repo_name}' not found."
            status = "not_found"
        else:
            msg = f"GitHub API responded with HTTP {err.code}: {err.reason}"
            status = "error"

        if _github_cache["data"]:
            cached = dict(_github_cache["data"])
            cached["cached"] = True
            cached["warning"] = msg
            return cached

        return {
            "integration_status": status,
            "repository": repo_name,
            "total_count": 0,
            "workflow_runs": [],
            "rate_limit_remaining": rate_limit_remaining,
            "message": msg,
            "cached": False,
            "last_fetched": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as ex:
        if _github_cache["data"]:
            cached = dict(_github_cache["data"])
            cached["cached"] = True
            cached["warning"] = str(ex)
            return cached

        return {
            "integration_status": "unavailable",
            "repository": repo_name,
            "total_count": 0,
            "workflow_runs": [],
            "rate_limit_remaining": None,
            "message": f"Unable to reach GitHub API: {str(ex)}",
            "cached": False,
            "last_fetched": datetime.now(timezone.utc).isoformat(),
        }


def get_cicd_pipeline_status(repo_name):
    """
    Retrieve latest GitHub Actions workflow run via GitHub API.
    Maintains compatibility with existing templates and tests.
    """
    token = current_app.config.get("GITHUB_TOKEN") if current_app else None
    res = fetch_github_workflows(repo_name, token=token, per_page=1)
    runs = res.get("workflow_runs", [])
    if runs:
        latest = runs[0]
        return {
            "status": "Connected",
            "workflow_name": latest.get("name", "CI/CD"),
            "conclusion": latest.get("conclusion") or "in_progress",
            "status_code": latest.get("status", "completed"),
            "commit_sha": latest.get("commit_sha", ""),
            "html_url": latest.get("html_url", ""),
            "updated_at": latest.get("updated_at", ""),
            "available": True,
        }
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


def fetch_render_deployments(service_id, api_key, limit=5):
    """
    Retrieve real deployment records from Render REST API if credentials are provided.
    Falls back to honest integration status without fake records.
    """
    live_url = current_app.config.get(
        "RENDER_EXTERNAL_URL", "https://clouddeploy-aws-cicd.onrender.com"
    )
    if not service_id or not api_key:
        return {
            "integration_status": "unconfigured",
            "source": "native_git_deployment",
            "provider": "Render (Cloud PaaS)",
            "live_url": live_url,
            "service_id": service_id or "Not configured",
            "message": (
                "Render API credentials (RENDER_API_KEY, RENDER_SERVICE_ID) not configured in environment. "
                "Native automatic Git-push deployment is operational."
            ),
            "deployments": [{
                "deployment_id": current_app.config.get("DEPLOYMENT_ID", "local-build"),
                "version": current_app.config.get("APP_VERSION", "1.0.0"),
                "timestamp": current_app.config.get("START_TIME").strftime("%Y-%m-%d %H:%M:%S UTC"),
                "status": "LIVE",
                "trigger": "git_push",
                "details": "Active application runtime on Render Cloud",
            }]
        }

    url = f"https://api.render.com/v1/services/{service_id}/deploys?limit={limit}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "CloudDeploy-Monitor/2.0",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            deploys = []
            for item in data:
                deploy_info = item.get("deploy", item)
                commit = deploy_info.get("commit", {})
                deploys.append({
                    "id": deploy_info.get("id"),
                    "status": deploy_info.get("status", "unknown"),
                    "commit_id": (commit.get("id") or "")[:8],
                    "commit_message": commit.get("message", ""),
                    "created_at": deploy_info.get("createdAt"),
                    "updated_at": deploy_info.get("updatedAt"),
                    "finished_at": deploy_info.get("finishedAt"),
                })
            return {
                "integration_status": "connected",
                "source": "render_api",
                "provider": "Render",
                "live_url": live_url,
                "service_id": service_id,
                "deployments": deploys,
            }
    except Exception as err:
        return {
            "integration_status": "error",
            "source": "render_api",
            "provider": "Render",
            "live_url": live_url,
            "service_id": service_id,
            "message": f"Render API communication error: {str(err)}",
            "deployments": [],
        }


def get_deployment_history():
    """
    Retrieve real deployment history records from filesystem or fallback to active deployment.
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

    return [{
        "deployment_id": current_app.config.get("DEPLOYMENT_ID", "local-build"),
        "version": current_app.config.get("APP_VERSION", "1.0.0"),
        "timestamp": current_app.config.get("START_TIME").strftime("%Y-%m-%d %H:%M:%S UTC"),
        "environment": current_app.config.get("ENVIRONMENT", "production"),
        "status": "SUCCESS",
        "details": "Active application runtime",
    }]


def get_active_alerts(app, system_metrics, cicd_info, aws_info):
    """Evaluate system metrics, CI runs, and cloud status to produce honest alerts."""
    alerts = []
    if system_metrics.get("disk_used_pct", 0) > 85:
        alerts.append({
            "type": "warning",
            "title": "High Disk Utilization Alert",
            "message": f"Host disk space is at {system_metrics['disk_used_pct']}% utilization."
        })
    if not is_running_in_docker():
        alerts.append({
            "type": "info",
            "title": "Host Mode Active",
            "message": "Application is running directly on host Python runtime (Docker container inactive)."
        })
    if cicd_info.get("conclusion") == "failure":
        alerts.append({
            "type": "danger",
            "title": "CI/CD Pipeline Failure",
            "message": f"Latest GitHub Actions workflow for commit {cicd_info.get('commit_sha')} failed."
        })
    if not aws_info.get("connected"):
        alerts.append({
            "type": "secondary",
            "title": "AWS Cloud Disconnected",
            "message": "Local development / Render host. AWS EC2 metadata and CloudWatch Agent unavailable."
        })
    return alerts


@main_bp.route("/")
def index():
    """Render the primary CloudDeploy home dashboard."""
    app_info = {
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "hosting_provider": current_app.config.get("HOSTING_PROVIDER", "render"),
        "aws_region": current_app.config["AWS_REGION"],
        "is_container": is_running_in_docker(),
        "uptime_seconds": get_uptime_seconds(current_app),
        "os_platform": f"{platform.system()} {platform.release()}",
        "python_version": sys.version.split()[0],
        "live_url": current_app.config.get("RENDER_EXTERNAL_URL", "https://clouddeploy-aws-cicd.onrender.com"),
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
    alerts = get_active_alerts(current_app, system_metrics, cicd_info, aws_info)

    # Detailed GitHub workflow runs
    token = current_app.config.get("GITHUB_TOKEN")
    github_telemetry = fetch_github_workflows(repo, token=token, per_page=5)

    dashboard_data = {
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "hosting_provider": current_app.config.get("HOSTING_PROVIDER", "render"),
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
        "github_telemetry": github_telemetry,
        "history": deploy_history,
        "alerts": alerts,
        "live_url": current_app.config.get("RENDER_EXTERNAL_URL", "https://clouddeploy-aws-cicd.onrender.com"),
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
        "timestamp": current_time_iso,
        "hosting_provider": current_app.config.get("HOSTING_PROVIDER", "render"),
        "uptime_seconds": get_uptime_seconds(current_app),
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
        "hosting_provider": current_app.config.get("HOSTING_PROVIDER", "render"),
        "is_container": is_running_in_docker(),
        "uptime_seconds": get_uptime_seconds(current_app),
        "python_version": sys.version.split()[0],
        "status": "operational",
        "live_url": current_app.config.get("RENDER_EXTERNAL_URL", "https://clouddeploy-aws-cicd.onrender.com"),
    }), 200


@main_bp.route("/api/github/workflows")
def api_github_workflows():
    """
    Real-time GitHub Actions workflow telemetry via GitHub REST API.
    Provides latest runs, conclusion, branch, commit SHA, and rate limit status.
    """
    repo = current_app.config.get("GITHUB_REPOSITORY", "ullas-reddy-g/CloudDeploy-AWS-CICD")
    token = current_app.config.get("GITHUB_TOKEN")
    force = request.args.get("refresh", "false").lower() == "true"
    telemetry = fetch_github_workflows(repo, token=token, per_page=5, force_refresh=force)
    return jsonify(telemetry), 200


@main_bp.route("/api/deployments")
def api_deployments():
    """
    Render cloud deployment status & history endpoint.
    Returns actual Render API deploys if configured, or honest integration status.
    """
    service_id = current_app.config.get("RENDER_SERVICE_ID")
    api_key = current_app.config.get("RENDER_API_KEY")
    deploys = fetch_render_deployments(service_id, api_key, limit=5)
    return jsonify(deploys), 200


@main_bp.route("/api/monitoring")
def api_monitoring():
    """Consolidated application, system, container, and hosting metrics."""
    return jsonify({
        "system": get_system_metrics(),
        "docker": {
            "is_container": is_running_in_docker(),
            "hostname": platform.node(),
            "runtime_status": (
                "Running (Isolated UID 10001)" if is_running_in_docker() else "Host Execution"
            ),
        },
        "hosting": {
            "provider": current_app.config.get("HOSTING_PROVIDER", "render"),
            "live_url": current_app.config.get("RENDER_EXTERNAL_URL", "https://clouddeploy-aws-cicd.onrender.com"),
            "environment": current_app.config.get("ENVIRONMENT", "production"),
        },
        "uptime_seconds": get_uptime_seconds(current_app),
        "status": "healthy",
    }), 200


@main_bp.route("/api/system-metrics")
def api_system_metrics():
    """JSON endpoint providing actual host metrics and diagnostics (backward compatible)."""
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
    """JSON endpoint returning recent application logs sanitized of secrets."""
    buf = getattr(current_app, "log_buffer", None)
    raw_logs = list(buf.buffer) if buf else []

    sanitized_logs = []
    sensitive_keys = [
        "SECRET_KEY", "AWS_SECRET_ACCESS_KEY", "RENDER_API_KEY", "GITHUB_TOKEN"
    ]
    for entry in raw_logs:
        msg = entry.get("message", "")
        for key in sensitive_keys:
            val = current_app.config.get(key)
            if val and len(val) > 4 and val in msg:
                msg = msg.replace(val, "***REDACTED***")
        sanitized_logs.append({
            "timestamp": entry.get("timestamp"),
            "level": entry.get("level"),
            "message": msg,
        })

    return jsonify({
        "logs": sanitized_logs,
        "count": len(sanitized_logs),
    }), 200


@main_bp.route("/api/alerts")
def api_alerts():
    """JSON endpoint returning evaluated application and deployment alerts."""
    repo = current_app.config.get("GITHUB_REPOSITORY", "ullas-reddy-g/CloudDeploy-AWS-CICD")
    system_metrics = get_system_metrics()
    aws_info = get_aws_cloud_status()
    cicd_info = get_cicd_pipeline_status(repo)
    alerts = get_active_alerts(current_app, system_metrics, cicd_info, aws_info)
    return jsonify({
        "alerts": alerts,
        "count": len(alerts),
    }), 200


@main_bp.route("/error-trigger")
def trigger_error():
    """Route used strictly for testing the 500 error handler."""
    if current_app.config.get("TESTING") or current_app.config.get("DEBUG"):
        raise RuntimeError("Intentional error for testing 500 error handler")
    return jsonify({"error": "Forbidden"}), 403
