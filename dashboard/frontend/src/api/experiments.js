const isDocker = window.location.hostname !== "localhost";
export const API_URL = isDocker
  ? "http://dashboard_api:8000"
  : "http://localhost:8000";

export async function fetchExperiments() {
  const res = await fetch(`${API_URL}/experiments`);
  return res.json();
}

export async function fetchMetrics() {
  const res = await fetch(`${API_URL}/metrics`);
  return res.json();
}

export async function fetchLogs() {
  const res = await fetch(`${API_URL}/logs`);
  return res.json();
}

export async function fetchHistory() {
  const res = await fetch(`${API_URL}/history`);
  return res.json();
}

export async function runExperiment(params) {
  const res = await fetch(`${API_URL}/experiments/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return res.json();
}

// --- Analytics endpoints ---

export async function fetchHistorySummary(experiment = null) {
  const params = experiment ? `?experiment=${experiment}` : "";
  const res = await fetch(`${API_URL}/history/summary${params}`);
  return res.json();
}

export async function fetchVulnsByProtocol(experiment = null) {
  const params = experiment ? `?experiment=${experiment}` : "";
  const res = await fetch(`${API_URL}/history/vulns-by-protocol${params}`);
  return res.json();
}

export async function fetchVulnsByType(experiment = null) {
  const params = experiment ? `?experiment=${experiment}` : "";
  const res = await fetch(`${API_URL}/history/vulns-by-type${params}`);
  return res.json();
}

export async function fetchVulnsByDevice(experiment = null) {
  const params = experiment ? `?experiment=${experiment}` : "";
  const res = await fetch(`${API_URL}/history/vulns-by-device${params}`);
  return res.json();
}

export async function fetchExecTimeDistribution(experiment = null) {
  const params = experiment ? `?experiment=${experiment}` : "";
  const res = await fetch(`${API_URL}/history/exec-time-distribution${params}`);
  return res.json();
}

export async function fetchCumulativeVulns(experiment = null) {
  const params = experiment ? `?experiment=${experiment}` : "";
  const res = await fetch(`${API_URL}/history/cumulative-vulns${params}`);
  return res.json();
}

export async function fetchStrategyComparison(experiment = null) {
  const params = experiment ? `?experiment=${experiment}` : "";
  const res = await fetch(`${API_URL}/history/strategy-comparison${params}`);
  return res.json();
}

export async function fetchAutomlScores(experiment = null) {
  const params = experiment ? `?experiment=${experiment}` : "";
  const res = await fetch(`${API_URL}/history/automl-scores${params}`);
  return res.json();
}
