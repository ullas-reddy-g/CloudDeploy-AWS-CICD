#!/bin/bash
# ==============================================================================
# CloudDeploy - Local Automated Test & Code Quality Runner
# ==============================================================================

set -euo pipefail

echo "======================================================================"
echo " CloudDeploy Local Test Suite Execution"
echo "======================================================================"

echo "[1/3] Running Flake8 Code Style and Syntax Verification..."
python -m flake8 app/ tests/ --count --max-line-length=120 --statistics
echo "Flake8 verification PASSED."

echo "[2/3] Executing Pytest Unit & Integration Tests with Coverage..."
python -m pytest -v --cov=app --cov-report=term-missing --cov-fail-under=80
echo "Pytest suite PASSED with >=80% coverage."

echo "[3/3] Checking Docker Compose Syntax (if docker installed)..."
if command -v docker &>/dev/null; then
    docker compose config -q
    echo "Docker compose configuration is valid."
else
    echo "Docker not installed in local environment (Skipping compose check)."
fi

echo "======================================================================"
echo " All Local Verification Steps Completed Successfully!"
echo "======================================================================"
