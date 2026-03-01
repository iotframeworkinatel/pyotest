const isDocker = window.location.hostname !== "localhost";
export const API_URL = isDocker
  ? "http://dashboard_api:8000"
  : "http://localhost:8000";

// --- Scanning ---

export async function startScan(network = "172.20.0.0/27", extraPorts = null) {
  const res = await fetch(`${API_URL}/api/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ network, extra_ports: extraPorts }),
  });
  return res.json();
}

export async function fetchScanStatus() {
  const res = await fetch(`${API_URL}/api/scan/status`);
  return res.json();
}

export async function fetchScanResults() {
  const res = await fetch(`${API_URL}/api/scan/results`);
  return res.json();
}

// --- Devices ---

export async function addDevice(ip, ports) {
  const res = await fetch(`${API_URL}/api/devices`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ip, ports }),
  });
  return res.json();
}

export async function fetchDevices() {
  const res = await fetch(`${API_URL}/api/devices`);
  return res.json();
}

export async function removeDevice(ip) {
  const res = await fetch(`${API_URL}/api/devices/${ip}`, { method: "DELETE" });
  return res.json();
}

// --- Test Generation ---

export async function generateTestSuite(params) {
  const res = await fetch(`${API_URL}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return res.json();
}

export async function fetchSuites() {
  const res = await fetch(`${API_URL}/api/suites`);
  return res.json();
}

export async function fetchSuite(suiteId) {
  const res = await fetch(`${API_URL}/api/suites/${suiteId}`);
  return res.json();
}

export async function exportSuite(suiteId, format = "json") {
  const res = await fetch(`${API_URL}/api/suites/${suiteId}/export?format=${format}`);
  return res.text();
}

export async function deleteSuite(suiteId) {
  const res = await fetch(`${API_URL}/api/suites/${suiteId}`, { method: "DELETE" });
  return res.json();
}

// --- Test Execution ---

export async function runSuite(suiteId) {
  const res = await fetch(`${API_URL}/api/suites/${suiteId}/run`, { method: "POST" });
  return res.json();
}

export async function fetchRunStatus(suiteId) {
  const res = await fetch(`${API_URL}/api/suites/${suiteId}/run/status`);
  return res.json();
}

export async function fetchResults() {
  const res = await fetch(`${API_URL}/api/results`);
  return res.json();
}

export async function fetchResult(filename) {
  const res = await fetch(`${API_URL}/api/results/${filename}`);
  return res.json();
}

// --- Auto-Train Loop ---

export async function startTrainLoop(suiteId, iterations = 3) {
  const res = await fetch(`${API_URL}/api/suites/${suiteId}/train-loop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ iterations }),
  });
  return res.json();
}

export async function fetchTrainLoopStatus(suiteId) {
  const res = await fetch(`${API_URL}/api/suites/${suiteId}/train-loop/status`);
  return res.json();
}

export async function cancelTrainLoop(suiteId) {
  const res = await fetch(`${API_URL}/api/suites/${suiteId}/train-loop/cancel`, {
    method: "POST",
  });
  return res.json();
}

// --- ML Insights ---

export async function fetchMlStatus() {
  const res = await fetch(`${API_URL}/api/ml/status`);
  return res.json();
}

export async function fetchMlMetrics() {
  const res = await fetch(`${API_URL}/api/ml/metrics`);
  return res.json();
}

export async function triggerRetrain() {
  const res = await fetch(`${API_URL}/api/ml/retrain`, { method: "POST" });
  return res.json();
}

// --- History & Analytics ---

export async function fetchHistorySummary() {
  const res = await fetch(`${API_URL}/api/history/summary`);
  return res.json();
}

export async function fetchVulnsByProtocol() {
  const res = await fetch(`${API_URL}/api/history/vulns-by-protocol`);
  return res.json();
}

export async function fetchVulnsByType() {
  const res = await fetch(`${API_URL}/api/history/vulns-by-type`);
  return res.json();
}

export async function fetchVulnsByDevice() {
  const res = await fetch(`${API_URL}/api/history/vulns-by-device`);
  return res.json();
}

// --- Infrastructure ---

export async function fetchLogs(tail = 80, filter = null) {
  const params = new URLSearchParams();
  if (tail) params.set("tail", tail);
  if (filter) params.set("filter", filter);
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API_URL}/api/logs${qs}`);
  return res.json();
}

export async function fetchDockerPs() {
  const res = await fetch(`${API_URL}/api/docker-ps`);
  return res.json();
}

export async function fetchProtocols() {
  const res = await fetch(`${API_URL}/api/protocols`);
  return res.json();
}

// --- Hypothesis Validation ---

export async function fetchIterationMetrics() {
  const res = await fetch(`${API_URL}/api/hypothesis/iteration-metrics`);
  return res.json();
}

export async function fetchModelEvolution() {
  const res = await fetch(`${API_URL}/api/hypothesis/model-evolution`);
  return res.json();
}

export async function fetchCompositionAnalysis() {
  const res = await fetch(`${API_URL}/api/hypothesis/composition-analysis`);
  return res.json();
}

export async function fetchStatisticalTests(protocol = null) {
  const qs = protocol ? `?protocol=${encodeURIComponent(protocol)}` : "";
  const res = await fetch(`${API_URL}/api/hypothesis/statistical-tests${qs}`);
  return res.json();
}

export async function fetchRecommendationEffectiveness() {
  const res = await fetch(`${API_URL}/api/hypothesis/recommendation-effectiveness`);
  return res.json();
}

export async function fetchProtocolConvergence() {
  const res = await fetch(`${API_URL}/api/hypothesis/protocol-convergence`);
  return res.json();
}

export async function fetchRiskCalibration() {
  const res = await fetch(`${API_URL}/api/hypothesis/risk-calibration`);
  return res.json();
}

// --- Architecture metadata ---

export async function fetchArchitectureMetadata() {
  const res = await fetch(`${API_URL}/architecture/metadata`);
  return res.json();
}
