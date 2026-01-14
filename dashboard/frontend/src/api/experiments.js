const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function runExperiment(mode) {
  const response = await fetch(`${API_URL}/run?mode=${mode}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Erro ao iniciar experimento (${mode})`);
  }
  return await response.json();
}

export async function fetchExperiments() {
  const response = await fetch(`${API_URL}/experiments`);
  if (!response.ok) {
    throw new Error("Erro ao buscar experimentos");
  }
  return await response.json();
}

export async function fetchMetrics() {
  const response = await fetch(`${API_URL}/metrics`);
  if (!response.ok) {
    throw new Error("Erro ao buscar métricas");
  }
  return await response.text();
}
