import { useState, useEffect, useRef } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  CartesianGrid,
} from "recharts";

function App() {
  const isDocker = window.location.hostname !== "localhost";
  const API_URL = isDocker
    ? "http://dashboard_api:8000"
    : "http://localhost:8000";

  const [activeTab, setActiveTab] = useState("dashboard");
  const [experiments, setExperiments] = useState([]);
  const [metrics, setMetrics] = useState([]);
  const [history, setHistory] = useState([]);
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(false);
  const [params, setParams] = useState({
    mode: "static",
    verbose: false,
    network: "172.20.0.0/27",
    output: "html",
    ports: "",
    test: false,
    automl: false,
  });
  const [isStreaming, setIsStreaming] = useState(false);
  const logRef = useRef(null);
  let logIntervalRef = useRef(null);

  // 🎨 Cores por tipo de container
  const containerColors = {
    scanner: "text-green-400",
    http: "text-yellow-300",
    ftp: "text-blue-400",
    mqtt: "text-purple-300",
    telnet: "text-pink-400",
    modbus: "text-orange-400",
    coap: "text-cyan-300",
    dashboard_ui: "text-gray-400",
  };

  // Mapeia o nome do container para cor
  const colorizeLog = (logs) => {
    return logs
      .split("\n")
      .map((line, i) => {
        const match = line.match(/=== \[(.*?)\] ===/);
        if (match) {
          const name = match[1];
          const key = Object.keys(containerColors).find((k) =>
            name.startsWith(k)
          );
          const color = containerColors[key] || "text-white";
          return `<span class="${color} font-semibold">${line}</span>`;
        }
        return `<span class="text-gray-300">${line}</span>`;
      })
      .join("\n");
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setParams((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const fetchAll = async () => {
    try {
      const [expRes, metRes, logRes, histRes] = await Promise.all([
        fetch(`${API_URL}/experiments`),
        fetch(`${API_URL}/metrics`),
        fetch(`${API_URL}/logs`),
        fetch(`${API_URL}/history`),
      ]);
      const [exps, mets, logs, hist] = await Promise.all([
        expRes.json(),
        metRes.json(),
        logRes.json(),
        histRes.json(),
      ]);
      setExperiments(exps.experiments || []);
      setMetrics(mets.metrics || []);
      setLogs(logs.logs || "Sem logs");
      setHistory(hist.history || []);
    } catch (err) {
      console.error("Erro:", err);
    }
  };

  const startLogStreaming = () => {
    if (isStreaming) return;
    setIsStreaming(true);
    logIntervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/logs`);
        const data = await res.json();
        setLogs(data.logs || data.error || "Sem logs...");
        if (logRef.current)
          logRef.current.scrollTop = logRef.current.scrollHeight;
      } catch (err) {
        setLogs("Erro ao obter logs: " + err.message);
      }
    }, 2000);
  };

  const stopLogStreaming = () => {
    setIsStreaming(false);
    clearInterval(logIntervalRef.current);
  };

  const runExperiment = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/experiments/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      const data = await res.json();
      alert(`Experimento iniciado:\n${data.command}`);
      startLogStreaming();
      setTimeout(fetchAll, 5000);
    } catch (err) {
      alert("Erro ao executar: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    const i = setInterval(fetchAll, 15000);
    return () => clearInterval(i);
  }, []);

  const chartData = metrics.map((m) => ({
    mode: m.mode,
    tests: m.tests_executed,
    vulns: m.vulns_detected,
    time: Math.round(m.exec_time_sec / 1000),
  }));

  return (
    <div className="min-h-screen bg-gray-100 text-gray-800 font-sans p-6">
      <h1 className="text-3xl font-bold mb-6 text-center">
        🧠 IoT Vulnerability Dashboard
      </h1>

      {/* Abas */}
      <div className="flex justify-center mb-6">
        {["dashboard", "history"].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-t-lg font-semibold ${
              activeTab === tab
                ? "bg-blue-600 text-white"
                : "bg-gray-300 text-gray-700 hover:bg-gray-400"
            }`}
          >
            {tab === "dashboard" ? "📊 Dashboard" : "📜 Histórico"}
          </button>
        ))}
      </div>

      {/* === DASHBOARD === */}
      {activeTab === "dashboard" && (
        <>
          {/* Configurações */}
          <div className="bg-white shadow-md rounded-2xl p-6 max-w-3xl mx-auto">
            <h2 className="text-xl font-semibold mb-4">
              ⚙️ Parâmetros do Experimento
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="flex flex-col">
                ⚙️ Mode
                <select
                  name="mode"
                  value={params.mode}
                  onChange={handleChange}
                  className="border rounded-md px-3 py-2 mt-1"
                >
                  <option value="static">Static</option>
                  <option value="automl">AutoML</option>
                </select>
              </label>

              <label className="flex flex-col">
                🌐 Network CIDR
                <input
                  type="text"
                  name="network"
                  value={params.network}
                  onChange={handleChange}
                  className="border rounded-md px-3 py-2 mt-1"
                />
              </label>

              <label className="flex flex-col">
                📦 Output Format
                <select
                  name="output"
                  value={params.output}
                  onChange={handleChange}
                  className="border rounded-md px-3 py-2 mt-1"
                >
                  <option value="html">HTML</option>
                  <option value="json">JSON</option>
                  <option value="csv">CSV</option>
                </select>
              </label>

              <label className="flex flex-col md:col-span-2">
                🔌 Ports (comma-separated)
                <input
                  type="text"
                  name="ports"
                  value={params.ports}
                  onChange={handleChange}
                  placeholder="80,443,8080"
                  className="border rounded-md px-3 py-2 mt-1"
                />
              </label>
            </div>

            <div className="flex flex-wrap gap-6 mt-5">
              {[
                ["verbose", "Verbose"],
                ["test", "Run Tests"],
                ["automl", "Enable AutoML"],
              ].map(([name, label]) => (
                <label key={name} className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    name={name}
                    checked={params[name]}
                    onChange={handleChange}
                    className="w-5 h-5 accent-blue-600"
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>

            <button
              onClick={runExperiment}
              disabled={loading}
              className={`mt-6 w-full py-3 font-semibold rounded-lg transition ${
                loading
                  ? "bg-gray-400 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-700 text-white"
              }`}
            >
              {loading ? "⏳ Executando..." : "🚀 Rodar Experimento"}
            </button>
          </div>

          {/* 📈 Métricas comparativas */}
          <div className="bg-white shadow-md rounded-2xl p-6 max-w-4xl mx-auto mt-10">
            <h2 className="text-xl font-semibold mb-4 text-center">
              📈 Métricas Comparativas
            </h2>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="mode" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="tests" fill="#60a5fa" name="Testes" />
                  <Bar dataKey="vulns" fill="#f87171" name="Vulnerabilidades" />
                  <Bar dataKey="time" fill="#34d399" name="Tempo (s)" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-center text-gray-500">
                Nenhuma métrica disponível.
              </p>
            )}
          </div>

          {/* Logs em tempo real */}
          <div className="bg-black mt-10 p-4 rounded-lg max-w-5xl mx-auto shadow-lg">
            <div className="flex justify-between items-center mb-3">
              <h2 className="text-lg font-semibold text-white">
                🪵 Logs em Tempo Real
              </h2>
              {isStreaming ? (
                <button
                  onClick={stopLogStreaming}
                  className="bg-red-600 text-white px-4 py-1 rounded-md hover:bg-red-700"
                >
                  Parar Logs
                </button>
              ) : (
                <button
                  onClick={startLogStreaming}
                  className="bg-blue-600 text-white px-4 py-1 rounded-md hover:bg-blue-700"
                >
                  Iniciar Logs
                </button>
              )}
            </div>
            <pre
              ref={logRef}
              className="bg-black text-sm overflow-y-scroll max-h-96 whitespace-pre-wrap border border-green-800 p-3 rounded-md"
              dangerouslySetInnerHTML={{ __html: colorizeLog(logs) }}
            ></pre>
          </div>
        </>
      )}

      {/* Histórico (mantido igual) */}
      {activeTab === "history" && (
        <div className="bg-white shadow-md rounded-2xl p-6 max-w-5xl mx-auto">
          <h2 className="text-xl font-semibold mb-6 text-center">
            📜 Histórico de Experimentos
          </h2>
          {history.length ? (
            <ul className="space-y-4">
              {history.map((h, i) => (
                <li
                  key={i}
                  className={`p-4 rounded-xl border-l-4 ${
                    h.mode === "automl"
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-500 bg-gray-50"
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <div>
                      <strong>
                        {h.mode === "automl" ? "🤖 AutoML" : "🧪 Static"}
                      </strong>{" "}
                      <span className="text-sm text-gray-500 ml-2">
                        {h.experiment}
                      </span>
                    </div>
                    <span className="text-sm text-gray-600">
                      ⏱ {Math.round(h.exec_time_sec / 1000)}s
                    </span>
                  </div>
                  <div className="mt-2 text-sm text-gray-700">
                    <p>Testes: {h.tests_executed}</p>
                    <p>Vulnerabilidades: {h.vulns_detected}</p>
                    <p>Devices: {h.devices}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-center text-gray-500">
              Nenhum histórico disponível.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
