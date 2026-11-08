# ==============================================================================
# CloudDeploy - Production Multi-Stage Dockerfile
# Base Image: Python 3.11 Slim
# Security: Non-root execution (UID 10001), Minimal attack surface
# ==============================================================================

FROM python:3.11-slim

# Build-time arguments
ARG APP_VERSION=1.0.0
ARG DEPLOYMENT_ID=local-build

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    ENVIRONMENT=production \
    APP_VERSION=${APP_VERSION} \
    DEPLOYMENT_ID=${DEPLOYMENT_ID}

# Install essential runtime utilities and create unprivileged application user
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 clouddeploy \
    && useradd -u 10001 -g clouddeploy -m -s /bin/bash clouddeploy

# Set working directory
WORKDIR /app

# Copy dependency specifications first to leverage Docker layer caching
COPY requirements.txt .

# Install production dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code into container
COPY app/ ./app/

# Set ownership of application files to non-root user
RUN chown -R clouddeploy:clouddeploy /app

# Switch to non-root user
USER clouddeploy

# Expose internal Gunicorn application port
EXPOSE 8000

# Container healthcheck using lightweight Python standard library probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).getcode() == 200 else 1)"

# Production execution via Gunicorn WSGI server
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
