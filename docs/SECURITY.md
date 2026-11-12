# CloudDeploy - Security Review & Architecture Audit

This document details the security posture, least-privilege principles, credential management, and runtime protections implemented in **CloudDeploy**.

---

## 1. Security Audit Findings

| Security Domain | Standard / Rule | Implementation & Audit Result | Status |
|---|---|---|---|
| **Credential Hygiene** | Zero hardcoded API keys or static credentials | No AWS access keys, Render API tokens, or GitHub personal access tokens exist in the source code or commit history. | **VERIFIED CLEAN** |
| **Environment Isolation** | Exclusion of local secret files | `.gitignore` strictly excludes `.env`, `*.pem`, `*.key`, `*.cert`, `venv/`, and `.pytest_cache/`. | **VERIFIED CLEAN** |
| **Container Privilege** | Non-root runtime execution | `Dockerfile` provisions an unprivileged system user `clouddeploy` with **UID 10001 / GID 10001** and executes via `USER clouddeploy`. | **VERIFIED CLEAN** |
| **HTTP Security Headers** | Header hardening on responses | Every response injects `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 1; mode=block`, and `Referrer-Policy: strict-origin-when-cross-origin`. | **VERIFIED CLEAN** |
| **Debug Protection** | Production debug disabled | `DEBUG=False` and `TESTING=False` are enforced by default in `ProductionConfig`. Route `/error-trigger` returns HTTP 403 Forbidden. | **VERIFIED CLEAN** |
| **Log Privacy** | In-memory log sanitization | The `/api/logs` handler automatically scrubs and redacts values matching `SECRET_KEY`, `AWS_SECRET_ACCESS_KEY`, `RENDER_API_KEY`, and `GITHUB_TOKEN`. | **VERIFIED CLEAN** |
| **OIDC Federation** | Passwordless cloud authentication | Optional AWS deployment workflows use OpenID Connect (OIDC) identity federation with repository-scoped trust (`repo:ullas-reddy-g/CloudDeploy-AWS-CICD:*`). | **VERIFIED CLEAN** |

---

## 2. Container Security & Non-Root Hardening

Running containerized workloads as `root` (UID 0) exposes the underlying host kernel to severe privilege escalation attacks. CloudDeploy enforces unprivileged execution at build time:

```dockerfile
# 1. Create dedicated system group and unprivileged user
RUN groupadd -g 10001 clouddeploy \
    && useradd -u 10001 -g clouddeploy -m -s /bin/bash clouddeploy

# 2. Transfer file ownership
RUN chown -R clouddeploy:clouddeploy /app

# 3. Drop all root capabilities
USER clouddeploy
```

Automated runtime verification in `.github/workflows/ci.yml` validates:
```bash
USER_ID=$(docker exec clouddeploy-test id -u)
[ "$USER_ID" -eq 10001 ]
```

---

## 3. Log Stream Sanitization

To prevent accidental credential disclosure in monitoring telemetry, `app/routes.py` filters sensitive strings from `RecentLogsHandler` before serializing JSON output:

```python
sensitive_keys = ["SECRET_KEY", "AWS_SECRET_ACCESS_KEY", "RENDER_API_KEY", "GITHUB_TOKEN"]
for key in sensitive_keys:
    val = current_app.config.get(key)
    if val and len(val) > 4 and val in message:
        message = message.replace(val, "***REDACTED***")
```

---

## 4. Reverse Proxy Hardening (Nginx)

Nginx provides front-line edge defense:
- `server_tokens off;` suppresses server version leakage.
- `client_max_body_size 16M;` prevents payload buffer exhaustion attacks.
- Upstream proxy timeouts limit slowloris connection-holding vectors.
- SSL termination readiness with modern TLS ciphers.
