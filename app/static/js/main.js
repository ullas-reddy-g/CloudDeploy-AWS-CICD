/**
 * CloudDeploy - Client-side Health & Diagnostics Monitor
 */
document.addEventListener("DOMContentLoaded", () => {
    const healthIndicator = document.getElementById("healthIndicator");
    const healthText = document.getElementById("healthText");
    const healthJsonOutput = document.getElementById("healthJsonOutput");
    const healthLatency = document.getElementById("healthLatency");
    const healthLastChecked = document.getElementById("healthLastChecked");
    const healthResponseCode = document.getElementById("healthResponseCode");
    const refreshBtn = document.getElementById("refreshHealthBtn");

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
            } else {
                if (healthText) healthText.textContent = "Degraded";
                if (healthIndicator) {
                    healthIndicator.className = "badge bg-warning-subtle text-warning border border-warning-subtle d-flex align-items-center gap-2 px-3 py-2";
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
            if (healthJsonOutput) {
                healthJsonOutput.textContent = JSON.stringify({ error: error.message, status: "offline" }, null, 2);
            }
            if (healthResponseCode) {
                healthResponseCode.textContent = "ERR_FAILED";
                healthResponseCode.className = "badge bg-danger";
            }
        }
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            if (healthText) healthText.textContent = "Checking...";
            probeHealth();
        });
    }

    // Initial probe
    probeHealth();

    // Auto-refresh every 30 seconds
    setInterval(probeHealth, 30000);
});
