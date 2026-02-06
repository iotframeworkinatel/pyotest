import React, { useState, useEffect, useMemo } from "react";

const COLORS = {
  scanner: "text-blue-400 border-blue-500",
  http_: "text-green-400 border-green-500",
  ftp_: "text-yellow-400 border-yellow-500",
  ssh_: "text-red-400 border-red-500",
  telnet_: "text-purple-400 border-purple-500",
  mqtt_: "text-pink-400 border-pink-500",
  modbus_: "text-orange-400 border-orange-500",
  coap_: "text-teal-400 border-teal-500",
  h2o: "text-cyan-400 border-cyan-500",
};

export default function LogsViewer({ apiUrl }) {
  const [logs, setLogs] = useState({});
  const [activeContainer, setActiveContainer] = useState(null);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const safeApiUrl =
    apiUrl || (window.location.hostname !== "localhost"
      ? "http://dashboard_api:8000"
      : "http://localhost:8000");

  async function fetchLogs() {
    try {
      setLoading(true);
      const res = await fetch(`${safeApiUrl}/logs`);
      const data = await res.json();
      setLogs(data.logs || {});
    } catch (err) {
      console.error("Erro ao buscar logs:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchLogs();
    const i = setInterval(fetchLogs, 5000);
    return () => clearInterval(i);
  }, []);

  const filteredContainers = useMemo(() => {
    return Object.keys(logs)
      .filter((name) => name.toLowerCase().includes(filter.toLowerCase()))
      .sort();
  }, [logs, filter]);

  const selectedLog =
    activeContainer && logs[activeContainer]
      ? logs[activeContainer]
      : "Selecione um container à esquerda para visualizar os logs.";

  return (
    <div className="flex flex-col md:flex-row bg-white shadow-md rounded-2xl overflow-hidden">
      {/* Lista lateral */}
      <div className="md:w-1/4 bg-gray-900 text-white p-4 border-r border-gray-700 flex flex-col">
        <h3 className="font-semibold mb-4 text-lg flex justify-between items-center">
          🧩 Containers
          {loading && <span className="text-xs text-gray-400">Atualizando…</span>}
        </h3>

        <input
          type="text"
          placeholder="Filtrar containers..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="mb-3 px-3 py-2 rounded-md bg-gray-800 text-sm text-gray-200 border border-gray-700 focus:outline-none focus:border-blue-500"
        />

        <ul className="space-y-2 overflow-y-auto max-h-[30rem]">
          {filteredContainers.map((name) => {
            const colorKey = Object.keys(COLORS).find((k) =>
              name.startsWith(k)
            );
            const color = COLORS[colorKey] || "text-white border-gray-600";
            const isActive = name === activeContainer;

            return (
              <li
                key={name}
                onClick={() => setActiveContainer(name)}
                className={`cursor-pointer px-3 py-2 rounded-lg border transition-colors ${
                  isActive
                    ? `bg-gray-800 ${color}`
                    : "hover:bg-gray-800 text-gray-300 border-gray-700"
                }`}
              >
                <span className="font-mono text-sm">{name}</span>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Logs */}
      <div className="flex-1 bg-black text-gray-200 p-4 overflow-y-auto max-h-[30rem] relative">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-lg font-semibold flex items-center">
            <span className="mr-2">🪵 Logs de:</span>
            <span className="text-blue-400 font-mono">
              {activeContainer || "—"}
            </span>
          </h3>
          {activeContainer && (
            <button
              onClick={fetchLogs}
              className="text-xs px-3 py-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white"
            >
              Atualizar agora
            </button>
          )}
        </div>
        <pre className="whitespace-pre-wrap text-sm leading-tight font-mono">
          {selectedLog}
        </pre>
      </div>
    </div>
  );
}
