const isDocker = window.location.hostname !== "localhost";
export const API_URL = isDocker
  ? "http://dashboard_api:8000"
  : "http://localhost:8000";

export async function fetchExperiments() {
  const res = await fetch(`${API_URL}/experiments`);
  return res.json();
}

export async function fetchLogs(tail = 80, filter = null) {
  const params = new URLSearchParams();
  if (tail) params.set("tail", tail);
  if (filter) params.set("filter", filter);
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API_URL}/logs${qs}`);
  return res.json();
}

export async function fetchExperimentStatus() {
  const res = await fetch(`${API_URL}/experiments/status`);
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

// --- Batch experiment runner ---

export async function startBatchRun({ mode = "automl", network = "172.20.0.0/27", runs = 30 }) {
  const res = await fetch(`${API_URL}/experiments/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, network, runs }),
  });
  return res.json();
}

export async function fetchBatchStatus() {
  const res = await fetch(`${API_URL}/experiments/batch/status`);
  return res.json();
}

// --- Statistical analysis ---

export async function fetchStatisticalAnalysis(experiments = null) {
  const qs = experiments ? `?experiments=${experiments.join(",")}` : "";
  const res = await fetch(`${API_URL}/experiments/analysis${qs}`);
  return res.json();
}

// --- Model metrics ---

export async function fetchModelMetrics() {
  const res = await fetch(`${API_URL}/experiments/model-metrics`);
  return res.json();
}

// --- Learning curve ---

export async function fetchLearningCurve() {
  const res = await fetch(`${API_URL}/experiments/learning-curve`);
  return res.json();
}

// --- Architecture metadata ---

export async function fetchArchitectureMetadata() {
  const res = await fetch(`${API_URL}/architecture/metadata`);
  return res.json();
}
