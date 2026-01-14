const { useState, useEffect } = React;

function App() {
  const isDocker = window.location.hostname !== "localhost";
  const API_URL = isDocker ? "http://dashboard_api:8000"  // usado quando o app roda dentro do Docker
  : "http://localhost:8000";     // usado quando acessado pelo navegador local

  const [msg, setMsg] = useState("🚀 IoT Vulnerability Dashboard pronto!");
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState("");

  // ------------------------------------------------------------
  // 🚀 Executa experimento (static / automl)
  // ------------------------------------------------------------
  async function runExperiment(mode) {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/experiments/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, network: "172.20.0.0/27" }),
      });

      const data = await res.json();
      alert(data.message || `Experimento ${mode} iniciado`);
      setTimeout(fetchExperiments, 5000); // atualiza lista depois de 5s
    } catch (err) {
      alert("Erro: " + err.message);
    } finally {
      setLoading(false);
    }
  }

  // ------------------------------------------------------------
  // 📊 Busca experimentos existentes
  // ------------------------------------------------------------
  async function fetchExperiments() {
    try {
      const res = await fetch(`${API_URL}/experiments`);
      const data = await res.json();
      setExperiments(data.experiments || []);
    } catch (err) {
      console.error("Erro ao buscar experimentos:", err);
    }
  }

  // ------------------------------------------------------------
  // 🪵 Logs do scanner
  // ------------------------------------------------------------
  async function fetchLogs() {
    try {
      const res = await fetch(`${API_URL}/logs`);
      const data = await res.json();
      setLogs(data.logs || "Sem logs disponíveis");
    } catch (err) {
      setLogs("Erro ao buscar logs: " + err.message);
    }
  }

  // ------------------------------------------------------------
  // 🔄 Inicialização
  // ------------------------------------------------------------
  useEffect(() => {
    fetchExperiments();
    fetchLogs();
    const interval = setInterval(fetchLogs, 10000);
    return () => clearInterval(interval);
  }, []);

  // ------------------------------------------------------------
  // 💅 Renderização
  // ------------------------------------------------------------
  return (
    <div style={{ padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>{msg}</h1>

      <div style={{ marginTop: "1rem" }}>
        <button disabled={loading} onClick={() => runExperiment("static")}>
          ⚙️ Rodar Static
        </button>
        <button
          disabled={loading}
          style={{ marginLeft: 10 }}
          onClick={() => runExperiment("automl")}
        >
          🤖 Rodar AutoML
        </button>
      </div>

      <h3 style={{ marginTop: "2rem" }}>📊 Experimentos</h3>
      <ul>
        {experiments.map((e, i) => (
          <li key={i}>{e}</li>
        ))}
      </ul>

      <h3 style={{ marginTop: "2rem" }}>🪵 Logs do Scanner</h3>
      <pre
        style={{
          background: "#f5f5f5",
          padding: 10,
          borderRadius: 5,
          maxHeight: 300,
          overflow: "auto",
        }}
      >
        {logs}
      </pre>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
