/**
 * CloudDeploy - Client-side Health, Diagnostics & Log Streaming Monitor
 */
document.addEventListener("DOMContentLoaded", () => {
    const healthIndicator = document.getElementById("healthIndicator");
    const healthText = document.getElementById("healthText");
    const healthJsonOutput = document.getElementById("healthJsonOutput");
    const infoJsonOutput = document.getElementById("infoJsonOutput");
    const healthLatency = document.getElementById("healthLatency");
    const healthLastChecked = document.getElementById("healthLastChecked");
    const healthResponseCode = document.getElementById("healthResponseCode");
    const refreshHealthBtn = document.getElementById("refreshHealthBtn");
    const refreshLogsBtn = document.getElementById("refreshLogsBtn");
    const applicationLogStream = document.getElementById("applicationLogStream");
    const logCountBadge = document.getElementById("logCountBadge");
    const overviewHealthBadge = document.getElementById("overviewHealthBadge");

    async function probeHealth() {
        const startTime = performance.now();
        try {
            const response = await fetch("/health", { cache: "no-store" });
            const endTime = performance.now();
            const latencyMs = Math.round(endTime - startTime);
            const data = await response.json();

            if (response.ok && data.status === "healthy") {
                if (healthText) healthText.textContent = "System Healthy";
                if (healthIndicator) {
                    healthIndicator.className = "badge bg-success-subtle text-success border border-success-subtle d-flex align-items-center gap-2 px-3 py-2";
                }
                if (overviewHealthBadge) {
                    overviewHealthBadge.textContent = "OPERATIONAL";
                    overviewHealthBadge.className = "badge bg-success-subtle text-success border border-success-subtle";
                }
            } else {
                if (healthText) healthText.textContent = "Degraded";
                if (healthIndicator) {
                    healthIndicator.className = "badge bg-warning-subtle text-warning border border-warning-subtle d-flex align-items-center gap-2 px-3 py-2";
                }
                if (overviewHealthBadge) {
                    overviewHealthBadge.textContent = "DEGRADED";
                    overviewHealthBadge.className = "badge bg-warning-subtle text-warning border border-warning-subtle";
                }
            }

            if (healthJsonOutput) {
                healthJsonOutput.textContent = JSON.stringify(data, null, 2);
            }
            if (healthLatency) {
                healthLatency.textContent = `${latencyMs} ms`;
            }
            if (healthLastChecked) {
                healthLastChecked.textContent = new Date().toLocaleTimeString();
            }
            if (healthResponseCode) {
                healthResponseCode.textContent = `HTTP ${response.status}`;
                healthResponseCode.className = response.ok ? "badge bg-success" : "badge bg-danger";
            }
        } catch (error) {
            if (healthText) healthText.textContent = "Unreachable";
            if (healthIndicator) {
                healthIndicator.className = "badge bg-danger-subtle text-danger border border-danger-subtle d-flex align-items-center gap-2 px-3 py-2";
            }
            if (overviewHealthBadge) {
                overviewHealthBadge.textContent = "OFFLINE";
                overviewHealthBadge.className = "badge bg-danger-subtle text-danger border border-danger-subtle";
            }
            if (healthJsonOutput) {
                healthJsonOutput.textContent = JSON.stringify({ error: error.message, status: "offline" }, null, 2);
            }
            if (healthResponseCode) {
                healthResponseCode.textContent = "ERR_FAILED";
                healthResponseCode.className = "badge bg-danger";
            }
        }
    }

    async function probeInfo() {
        if (!infoJsonOutput) return;
        try {
            const resp = await fetch("/api/info", { cache: "no-store" });
            const data = await resp.json();
            infoJsonOutput.textContent = JSON.stringify(data, null, 2);
        } catch (err) {
            infoJsonOutput.textContent = JSON.stringify({ error: err.message }, null, 2);
        }
    }

    async function probeLogs() {
        if (!applicationLogStream) return;
        try {
            const resp = await fetch("/api/logs", { cache: "no-store" });
            const data = await resp.json();
            const logs = data.logs || [];

            if (logCountBadge) {
                logCountBadge.textContent = `${logs.length} entries`;
            }

            if (logs.length === 0) {
                applicationLogStream.textContent = "No log records accumulated yet.";
                return;
            }

            const formatted = logs.map(l => {
                const color = l.level === "ERROR" ? "text-danger" : (l.level === "WARNING" ? "text-warning" : "text-light");
                return `[${l.timestamp}] [${l.level}] ${l.message}`;
            }).join("\n");

            applicationLogStream.textContent = formatted;
            applicationLogStream.scrollTop = applicationLogStream.scrollHeight;
        } catch (err) {
            applicationLogStream.textContent = `Error loading log stream: ${err.message}`;
        }
    }

    if (refreshHealthBtn) {
        refreshHealthBtn.addEventListener("click", () => {
            if (healthText) healthText.textContent = "Checking...";
            probeHealth();
            probeInfo();
        });
    }

    if (refreshLogsBtn) {
        refreshLogsBtn.addEventListener("click", () => {
            probeLogs();
        });
    }

    // Initial triggers
    probeHealth();
    probeInfo();
    probeLogs();

    // Auto-refresh loops
    setInterval(probeHealth, 30000);
    setInterval(probeLogs, 15000);
});
