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
