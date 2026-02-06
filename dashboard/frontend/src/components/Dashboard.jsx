import { useState } from "react";
import { runExperiment } from "../api/experiments";
import MetricsChart from "./MetricsChart";
import LogsViewer from "./LogsViewer";

export default function Dashboard({ metrics, apiUrl, refreshAll }) {
  const [loading, setLoading] = useState(false);
  const [showLogs, setShowLogs] = useState(true);

  const [params, setParams] = useState({
    mode: "automl",
    verbose: false,
    network: "172.20.0.0/27",
    output: "html",
    ports: "",
    test: false,
    automl: true,
  });

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setParams((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const run = async () => {
    setLoading(true);
    try {
      const data = await runExperiment(params);
      alert(`Experimento iniciado:\n${data.command}`);
      setTimeout(refreshAll, 5000);
    } catch (err) {
      alert("Erro: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* PARÂMETROS */}
      <div className="bg-white shadow-md rounded-2xl p-6 max-w-3xl mx-auto mb-8">
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
          onClick={run}
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

      {/* MÉTRICAS */}
      <MetricsChart metrics={metrics} />

      {/* LOGS */}
      <div className="max-w-5xl mx-auto mt-10">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">🪵 Logs em Tempo Real</h2>
          <button
            onClick={() => setShowLogs((v) => !v)}
            className="text-sm px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white"
          >
            {showLogs ? "Ocultar Logs" : "Mostrar Logs"}
          </button>
        </div>
        {showLogs && <LogsViewer apiUrl={apiUrl} />}
      </div>
    </>
  );
}
