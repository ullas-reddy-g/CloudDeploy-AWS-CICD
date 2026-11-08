#!/bin/bash
# ==============================================================================
# CloudDeploy - Remote / Local Smoke Test Probe
# ==============================================================================

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

echo "======================================================================"
echo " CloudDeploy Smoke Test Runner"
echo " Target Endpoint: $BASE_URL"
echo "======================================================================"

probe_endpoint() {
    local path="$1"
    local expected_code="$2"
    local full_url="${BASE_URL}${path}"

    echo -n "Testing $path (Expected HTTP $expected_code)... "
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "$full_url" || echo "000")

    if [ "$http_code" -eq "$expected_code" ]; then
        echo "SUCCESS (HTTP $http_code)"
    else
        echo "FAILED (Received HTTP $http_code)"
        return 1
    fi
}

probe_endpoint "/" 200
probe_endpoint "/health" 200
probe_endpoint "/api/info" 200
probe_endpoint "/deployment" 200
probe_endpoint "/about" 200
probe_endpoint "/non-existent-404-check" 404

echo "======================================================================"
echo " All Smoke Tests Passed for $BASE_URL!"
echo "======================================================================"
