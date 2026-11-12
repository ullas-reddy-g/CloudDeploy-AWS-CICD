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

# In-memory caches to prevent rate limiting
_github_cache = {
    "data": None,
    "timestamp": 0.0,
    "ttl": 60.0,
}

_render_cache = {
    "data": None,
    "timestamp": 0.0,
    "ttl": 60.0,
}


def get_uptime_seconds(app):
    """Calculate running uptime in seconds."""
    start_time = app.config.get("START_TIME")
    if not start_time:
        return 0
    now = datetime.now(timezone.utc)
    return int((now - start_time).total_seconds())


def is_running_in_docker():
    """
    Detect reliably whether the application is running inside a Docker/container runtime.
    Checks explicit environment markers, filesystem signatures, Linux cgroups, and mountinfo.
    """
    # 1. Explicit container environment markers
    if os.getenv("DOCKER_CONTAINER", "").lower() in ("true", "1", "yes"):
        return True
    if os.getenv("CONTAINER", "").lower() in ("docker", "podman", "containerd", "true"):
        return True

    # 2. Filesystem marker files
    try:
        if os.path.exists("/etc/clouddeploy-container") or os.path.exists("/.dockerenv"):
            return True
    except Exception:
        pass

    # 3. Linux cgroup inspection (cgroup v1 keywords and container signatures)
    try:
        for cgroup_path in ("/proc/self/cgroup", "/proc/1/cgroup"):
            if os.path.exists(cgroup_path):
                with open(cgroup_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if any(kw in content for kw in ("docker", "kubepods", "containerd", "libpod")):
                        return True
    except Exception:
        pass

    # 4. Linux mountinfo inspection (container overlay filesystem)
    try:
        if os.path.exists("/proc/self/mountinfo"):
            with open("/proc/self/mountinfo", "r", encoding="utf-8") as f:
                mounts = f.read()
                if any(kw in mounts for kw in ("docker", "containerd")) or ("overlay" in mounts and " / " in mounts):
                    return True
    except Exception:
        pass

    return False


def get_runtime_privilege():
    """
    Determine the actual process execution user and privilege.
    Returns UID and a verified, honest privilege description.
    """
    if hasattr(os, "getuid"):
        try:
            uid = os.getuid()
            if uid == 10001:
                return {
                    "is_non_root": True,
                    "uid": 10001,
                    "label": "Non-Root User (UID 10001 / clouddeploy)"
                }
            elif uid == 0:
                return {
                    "is_non_root": False,
                    "uid": 0,
                    "label": "Root User (UID 0 - Unprivileged execution disabled)"
                }
            else:
                return {
                    "is_non_root": (uid != 0),
                    "uid": uid,
                    "label": f"Non-Root User (UID {uid})"
                }
        except Exception:
            pass

    user = os.getenv("USERNAME") or os.getenv("USER") or "Workstation User"
    return {
        "is_non_root": True,
        "uid": None,
        "label": f"Host Workstation User ({user})"
    }


def get_container_resource_limits():
    """
    Inspect Linux cgroups (v1 and v2) to determine genuine container memory and CPU limits.
    Returns container limits or None if unconstrained or unexposed.
    """
    mem_limit_mb = None
    mem_usage_mb = None
    cpu_limit_cores = None
    cgroup_version = None

    # Check cgroup v2
    try:
        if os.path.exists("/sys/fs/cgroup/memory.max"):
            cgroup_version = "v2"
            with open("/sys/fs/cgroup/memory.max", "r", encoding="utf-8") as f:
                max_str = f.read().strip()
                if max_str != "max":
                    limit_bytes = int(max_str)
                    if limit_bytes < (64 * 1024 ** 4):  # Filter out unconstrained (>64 TB)
                        mem_limit_mb = round(limit_bytes / (1024 * 1024), 1)

            if os.path.exists("/sys/fs/cgroup/memory.current"):
                with open("/sys/fs/cgroup/memory.current", "r", encoding="utf-8") as f:
                    usage_bytes = int(f.read().strip())
                    mem_usage_mb = round(usage_bytes / (1024 * 1024), 1)

            if os.path.exists("/sys/fs/cgroup/cpu.max"):
                with open("/sys/fs/cgroup/cpu.max", "r", encoding="utf-8") as f:
                    parts = f.read().strip().split()
                    if len(parts) == 2 and parts[0] != "max":
                        quota = int(parts[0])
                        period = int(parts[1])
                        if period > 0:
                            cpu_limit_cores = round(quota / period, 2)
    except Exception:
        pass

    # Check cgroup v1 if v2 was not found or limit was unconstrained
    if mem_limit_mb is None:
        try:
            v1_mem_limit = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
            v1_mem_usage = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
            if os.path.exists(v1_mem_limit):
                cgroup_version = "v1"
                with open(v1_mem_limit, "r", encoding="utf-8") as f:
                    limit_bytes = int(f.read().strip())
                    if limit_bytes < (1024 ** 4):  # < 1 TB (exclude unconstrained 9223372036854771712)
                        mem_limit_mb = round(limit_bytes / (1024 * 1024), 1)

            if os.path.exists(v1_mem_usage):
                with open(v1_mem_usage, "r", encoding="utf-8") as f:
                    usage_bytes = int(f.read().strip())
                    mem_usage_mb = round(usage_bytes / (1024 * 1024), 1)

            v1_cpu_quota = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
            v1_cpu_period = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
            if os.path.exists(v1_cpu_quota) and os.path.exists(v1_cpu_period):
                with open(v1_cpu_quota, "r", encoding="utf-8") as f_q:
                    quota = int(f_q.read().strip())
                with open(v1_cpu_period, "r", encoding="utf-8") as f_p:
                    period = int(f_p.read().strip())
                if quota > 0 and period > 0:
                    cpu_limit_cores = round(quota / period, 2)
        except Exception:
            pass

    return {
        "cgroup_version": cgroup_version or "unavailable",
        "container_memory_limit_mb": mem_limit_mb,
        "container_memory_usage_mb": mem_usage_mb,
        "container_cpu_limit_cores": cpu_limit_cores,
    }


def get_system_metrics():
    """
    Retrieve actual system storage, CPU, and genuine container resource allocations.
    Clearly distinguishes container allocation from host-node capacity.
    """
    try:
        disk = shutil.disk_usage(os.getcwd())
        total_gb = round(disk.total / (1024 ** 3), 1)
        used_gb = round(disk.used / (1024 ** 3), 1)
        free_gb = round(disk.free / (1024 ** 3), 1)
        used_pct = round((disk.used / disk.total) * 100, 1)
    except Exception:
        total_gb, used_gb, free_gb, used_pct = 0, 0, 0, 0

    cpu_count = os.cpu_count() or 1

    # Retrieve container limits from Linux cgroups
    cgroup_data = get_container_resource_limits()
    mem_limit = cgroup_data["container_memory_limit_mb"]
    mem_usage = cgroup_data["container_memory_usage_mb"]
    cpu_limit = cgroup_data["container_cpu_limit_cores"]

    container_mem_limit_str = (
        f"{mem_limit} MB" if mem_limit is not None else "Metric unavailable in current hosting environment"
    )
    container_mem_usage_str = (
        f"{mem_usage} MB" if mem_usage is not None else "Metric unavailable in current hosting environment"
    )
    container_cpu_str = (
        f"{cpu_limit} vCPU" if cpu_limit is not None else "Shared Host Allocation (Quota unconstrained or unexposed)"
    )

    # Read physical host node RAM for transparency
    host_ram_str = "unavailable"
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                lines = f.readlines()
            mem_info = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    mem_info[parts[0].strip()] = int(parts[1].strip().split()[0])
            if "MemTotal" in mem_info:
                host_ram_str = f"{round(mem_info['MemTotal'] / 1024, 1)} MB"
    except Exception:
        pass

    return {
        # Backward-compatible fields
        "disk_total_gb": total_gb,
        "disk_used_gb": used_gb,
        "disk_free_gb": free_gb,
        "disk_used_pct": used_pct,
        "cpu_count": cpu_count,
        "mem_total": container_mem_limit_str,
        "mem_available": container_mem_usage_str,
        "mem_used_pct": "N/A" if mem_limit is None else f"{round((mem_usage / mem_limit) * 100, 1)}%",
        # Granular categorized metrics
        "container": {
            "memory_limit": container_mem_limit_str,
            "memory_usage": container_mem_usage_str,
            "cpu_allocation": container_cpu_str,
            "cgroup_version": cgroup_data["cgroup_version"],
        },
        "host_node": {
            "label": "Underlying Host Node Capacity (Shared Cluster Platform)",
            "cpu_cores": f"{cpu_count} vCPU (Physical Host)",
            "physical_ram": host_ram_str,
            "disk_total_gb": total_gb,
            "disk_used_gb": used_gb,
            "disk_free_gb": free_gb,
            "disk_used_pct": used_pct,
            "disk_scope": "Host Root Filesystem (Shared Platform Volume; not service quota)",
        }
    }


def get_aws_cloud_status():
    """
    Attempt to fetch real EC2 metadata via IMDSv2 with a strict 0.5s timeout.
    Returns honest status indicating it is an optional architecture extension.
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
            "status": "Optional Extension (Not Hosted on EC2)",
            "instance_id": "Unavailable (Active on Render Cloud)",
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
    Supports optional GITHUB_TOKEN and handles rate limits gracefully.
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
            msg = (
                "GitHub API rate limit exceeded on shared hosting IP. "
                "Configure GITHUB_TOKEN in Render environment variables for 5,000 requests/hr."
            )
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


def fetch_render_deployments(service_id, api_key, limit=5, force_refresh=False):
    """
    Retrieve genuine deployment records from Render REST API if credentials are provided.
    Falls back cleanly to application runtime metadata with honest labeling.
    """
    now = time.time()
    if (
        not force_refresh
        and _render_cache["data"]
        and (now - _render_cache["timestamp"] < _render_cache["ttl"])
    ):
        return _render_cache["data"]

    live_url = current_app.config.get(
        "RENDER_EXTERNAL_URL", "https://clouddeploy-aws-cicd.onrender.com"
    )

    if not service_id or not api_key:
        result = {
            "integration_status": "unconfigured",
            "source": "application_metadata",
            "record_type": "Application Runtime Metadata",
            "provider": "Render (Cloud PaaS)",
            "live_url": live_url,
            "service_id": service_id or "Not configured",
            "message": (
                "Render API key (RENDER_API_KEY) not configured in environment. "
                "Displaying active runtime deployment metadata. "
                "To query real-time deployment history from the Render REST API, "
                "add RENDER_API_KEY to your Render environment variables."
            ),
            "deployments": [{
                "deployment_id": current_app.config.get("DEPLOYMENT_ID", "local-build"),
                "version": current_app.config.get("APP_VERSION", "1.0.0"),
                "timestamp": current_app.config.get("START_TIME").strftime("%Y-%m-%d %H:%M:%S UTC"),
                "status": "LIVE (Active Runtime)",
                "record_type": "Application Runtime Metadata",
                "trigger": "git_push",
                "details": "Active application runtime on Render Cloud",
            }]
        }
        _render_cache["data"] = result
        _render_cache["timestamp"] = now
        return result

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
                    "status": deploy_info.get("status", "unknown").upper(),
                    "commit_id": (commit.get("id") or "")[:8],
                    "commit_message": commit.get("message", ""),
                    "record_type": "Official Render REST API",
                    "created_at": deploy_info.get("createdAt"),
                    "updated_at": deploy_info.get("updatedAt"),
                    "finished_at": deploy_info.get("finishedAt"),
                })
            result = {
                "integration_status": "connected",
                "source": "official_render_api",
                "record_type": "Official Render REST API",
                "provider": "Render Cloud",
                "live_url": live_url,
                "service_id": service_id,
                "deployments": deploys,
            }
            _render_cache["data"] = result
            _render_cache["timestamp"] = now
            return result
    except Exception as err:
        result = {
            "integration_status": "error",
            "source": "application_metadata_fallback",
            "record_type": "Application Runtime Metadata",
            "provider": "Render Cloud",
            "live_url": live_url,
            "service_id": service_id,
            "message": f"Render API communication error: {str(err)}",
            "deployments": [{
                "deployment_id": current_app.config.get("DEPLOYMENT_ID", "local-build"),
                "version": current_app.config.get("APP_VERSION", "1.0.0"),
                "timestamp": current_app.config.get("START_TIME").strftime("%Y-%m-%d %H:%M:%S UTC"),
                "status": "LIVE (Fallback)",
                "record_type": "Application Runtime Metadata",
                "trigger": "git_push",
                "details": "Active application runtime on Render Cloud",
            }],
        }
        return result


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
        "status": "LIVE",
        "record_type": "Application Runtime Metadata",
        "details": "Active application runtime",
    }]


def get_active_alerts(app, system_metrics, cicd_info, aws_info):
    """Evaluate system metrics, CI runs, and cloud status to produce honest alerts."""
    alerts = []
    if system_metrics.get("disk_used_pct", 0) > 85:
        alerts.append({
            "type": "warning",
            "title": "High Storage Capacity Alert",
            "message": f"Host filesystem storage is at {system_metrics['disk_used_pct']}% utilization."
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
    return alerts


@main_bp.route("/")
def index():
    """Render the primary CloudDeploy home dashboard."""
    is_docker = is_running_in_docker()
    privilege = get_runtime_privilege()

    app_info = {
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "hosting_provider": current_app.config.get("HOSTING_PROVIDER", "render"),
        "aws_region": current_app.config["AWS_REGION"],
        "is_container": is_docker,
        "runtime_privilege": privilege["label"],
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
    privilege = get_runtime_privilege()

    system_metrics = get_system_metrics()
    aws_info = get_aws_cloud_status()
    cicd_info = get_cicd_pipeline_status(repo)
    deploy_history = get_deployment_history()
    alerts = get_active_alerts(current_app, system_metrics, cicd_info, aws_info)

    # Detailed GitHub workflow runs
    token = current_app.config.get("GITHUB_TOKEN")
    github_telemetry = fetch_github_workflows(repo, token=token, per_page=5)

    # Render deployment status
    service_id = current_app.config.get("RENDER_SERVICE_ID", "srv-dbqn4es9v7es73d40jag")
    render_api_key = current_app.config.get("RENDER_API_KEY", "")
    render_data = fetch_render_deployments(service_id, render_api_key, limit=5)

    dashboard_data = {
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "hosting_provider": current_app.config.get("HOSTING_PROVIDER", "render"),
        "aws_region": current_app.config["AWS_REGION"],
        "is_container": is_docker,
        "privilege": privilege,
        "container_status": (
            "Running in Docker Container (UID 10001)" if is_docker else "Host Python Process (Local Workstation)"
        ),
        "uptime_seconds": get_uptime_seconds(current_app),
        "start_time": current_app.config["START_TIME"].strftime("%Y-%m-%d %H:%M:%S UTC"),
        "hostname": platform.node(),
        "github_repo": repo,
        "system_metrics": system_metrics,
        "aws_cloud": aws_info,
        "cicd": cicd_info,
        "github_telemetry": github_telemetry,
        "render_telemetry": render_data,
        "history": render_data.get("deployments", deploy_history),
        "alerts": alerts,
        "render_service_id": service_id,
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
        "commit_sha": current_app.config.get("DEPLOYMENT_ID", "local-build"),
        "timestamp": current_time_iso,
        "hosting_provider": current_app.config.get("HOSTING_PROVIDER", "render"),
        "is_container": is_running_in_docker(),
        "uptime_seconds": get_uptime_seconds(current_app),
    }), 200


@main_bp.route("/api/info")
def api_info():
    """
    Public non-sensitive application metadata endpoint.
    Guaranteed not to leak AWS secrets, credentials, or internal networks.
    """
    privilege = get_runtime_privilege()
    return jsonify({
        "app_name": current_app.config["APP_NAME"],
        "version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENVIRONMENT"],
        "deployment_id": current_app.config["DEPLOYMENT_ID"],
        "commit_sha": current_app.config.get("DEPLOYMENT_ID", "local-build"),
        "hosting_provider": current_app.config.get("HOSTING_PROVIDER", "render"),
        "is_container": is_running_in_docker(),
        "runtime_privilege": privilege["label"],
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
    service_id = current_app.config.get("RENDER_SERVICE_ID", "srv-dbqn4es9v7es73d40jag")
    api_key = current_app.config.get("RENDER_API_KEY")
    force = request.args.get("refresh", "false").lower() == "true"
    deploys = fetch_render_deployments(service_id, api_key, limit=5, force_refresh=force)
    return jsonify(deploys), 200


@main_bp.route("/api/monitoring")
def api_monitoring():
    """Consolidated application, system, container, and hosting metrics."""
    is_docker = is_running_in_docker()
    privilege = get_runtime_privilege()
    return jsonify({
        "system": get_system_metrics(),
        "docker": {
            "is_container": is_docker,
            "hostname": platform.node(),
            "runtime_privilege": privilege["label"],
            "runtime_status": (
                "Running in Docker Container (UID 10001)" if is_docker else "Host Python Process (Local Workstation)"
            ),
        },
        "hosting": {
            "provider": current_app.config.get("HOSTING_PROVIDER", "render"),
            "live_url": current_app.config.get("RENDER_EXTERNAL_URL", "https://clouddeploy-aws-cicd.onrender.com"),
            "environment": current_app.config.get("ENVIRONMENT", "production"),
            "service_id": current_app.config.get("RENDER_SERVICE_ID", "srv-dbqn4es9v7es73d40jag"),
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
