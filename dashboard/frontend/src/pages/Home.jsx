import Dashboard from "../components/Dashboard";
import History from "../components/History";
import StatisticalAnalysis from "../components/StatisticalAnalysis";
import { useDashboardData } from "../hooks/useDashboardData";
import { useState } from "react";
import { LayoutDashboard, History as HistoryIcon, FlaskConical } from "lucide-react";
import pyotestLogo from "../../resources/pyotest_logo.png"

const isDocker = window.location.hostname !== "localhost";
const API_URL = isDocker
  ? "http://dashboard_api:8000"
  : "http://localhost:8000";

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "history", label: "Histórico", icon: HistoryIcon },
  { id: "stats", label: "Análise Estatística", icon: FlaskConical },
];

export default function Home() {
  const { metrics, refreshAll } = useDashboardData();
  const [activeTab, setActiveTab] = useState("dashboard");

  return (
    <div className="min-h-screen bg-gray-100 text-gray-800 font-sans">
      {/* Top navbar */}
      <header className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <span className="text-2xl">
              <img
                src={pyotestLogo}
                alt="PyoTestLogo"
                className="inline w-8 h-8 object-contain"
              />
            </span>
            PYoTest
            <span className="text-sm font-normal text-gray-400 ml-1">
              IoT Vulnerability Scanner
            </span>
          </h1>

          <nav className="flex gap-1 bg-gray-100 rounded-xl p-1">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === id
                    ? id === "stats"
                      ? "bg-white text-violet-600 shadow-sm"
                      : "bg-white text-blue-600 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === "dashboard" && (
          <Dashboard
            refreshAll={refreshAll}
            apiUrl={API_URL}
            onNavigateToStats={() => setActiveTab("stats")}
          />
        )}
        {activeTab === "history" && <History />}
        {activeTab === "stats" && <StatisticalAnalysis />}
      </main>
    </div>
  );
}
