import Dashboard from "../components/Dashboard";
import Logs from "../components/LogsViewer";
import History from "../components/History";
import { useDashboardData } from "../hooks/useDashboardData";
import { useState } from "react";

const isDocker = window.location.hostname !== "localhost";
const API_URL = isDocker
  ? "http://dashboard_api:8000"
  : "http://localhost:8000";

export default function Home() {
  const {
    metrics,
    history,
    logs,
    logRef,
    isStreaming,
    startLogStreaming,
    stopLogStreaming,
    refreshAll,
  } = useDashboardData();

  const [activeTab, setActiveTab] = useState("dashboard");

  return (
    <div className="min-h-screen bg-gray-100 text-gray-800 font-sans p-6">
      <h1 className="text-3xl font-bold mb-6 text-center">
        🧠 PYoTest - IoT Vulnerability Dashboard
      </h1>

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

      {activeTab === "dashboard" && (
          <Dashboard
            metrics={metrics}
            refreshAll={refreshAll}
            apiUrl={API_URL}
            startLogStreaming={startLogStreaming}
          />
        )}

      {activeTab === "history" && <History history={history} />}
    </div>
  );
}
