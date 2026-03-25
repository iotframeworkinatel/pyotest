import TestGenerator from "../components/TestGenerator";
import TestSuites from "../components/TestSuites";
import Results from "../components/Results";
import Hypothesis from "../components/Hypothesis";
import Architecture from "../components/Architecture";
import { useState, useEffect } from "react";
import { Wand2, ListChecks, BarChart3, FlaskConical, Network } from "lucide-react";
import emergenceLogo from "../../resources/emergence_logo.png"

const API_URL = `http://${window.location.hostname}:8080`;

const TABS = [
  { id: "generator", label: "Generator", icon: Wand2, color: "blue" },
  { id: "suites", label: "Test Suites", icon: ListChecks, color: "violet" },
  { id: "results", label: "Results", icon: BarChart3, color: "orange" },
  { id: "hypothesis", label: "Hypothesis", icon: FlaskConical, color: "amber" },
  { id: "architecture", label: "Architecture", icon: Network, color: "emerald" },
];

const TAB_COLORS = {
  blue: "bg-white text-blue-600 shadow-sm",
  violet: "bg-white text-violet-600 shadow-sm",
  orange: "bg-white text-orange-600 shadow-sm",
  amber: "bg-white text-amber-600 shadow-sm",
  emerald: "bg-white text-emerald-600 shadow-sm",
};

export default function Home() {
  const [activeTab, setActiveTab] = useState("generator");

  // When the active tab changes, fire a resize event after a short delay
  // so Recharts ResponsiveContainer recalculates chart dimensions for the
  // newly-visible tab panel.
  useEffect(() => {
    const timer = setTimeout(() => {
      window.dispatchEvent(new Event("resize"));
    }, 60);
    return () => clearTimeout(timer);
  }, [activeTab]);

  return (
    <div className="min-h-screen bg-gray-100 text-gray-800 font-sans">
      {/* Top navbar */}
      <header className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <span className="text-2xl">
              <img
                src={emergenceLogo}
                alt="EmergenceLogo"
                className="inline w-8 h-8 object-contain"
              />
            </span>
            Emergence
            <span className="text-sm font-normal text-gray-400 ml-1">
              IoT Test Case Generator
            </span>
          </h1>

          <nav className="flex gap-1 bg-gray-100 rounded-xl p-1">
            {TABS.map(({ id, label, icon: Icon, color }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  activeTab === id
                    ? TAB_COLORS[color]
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

      {/* Content — all tabs stay mounted; hidden via CSS so state persists */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        <div style={{ display: activeTab === "generator" ? "block" : "none" }}>
          <TestGenerator
            apiUrl={API_URL}
            onSuiteGenerated={() => setActiveTab("suites")}
          />
        </div>
        <div style={{ display: activeTab === "suites" ? "block" : "none" }}>
          <TestSuites apiUrl={API_URL} onRunSuite={() => setActiveTab("results")} visible={activeTab === "suites"} />
        </div>
        <div style={{ display: activeTab === "results" ? "block" : "none" }}>
          <Results apiUrl={API_URL} visible={activeTab === "results"} />
        </div>
        <div style={{ display: activeTab === "hypothesis" ? "block" : "none" }}>
          <Hypothesis apiUrl={API_URL} visible={activeTab === "hypothesis"} />
        </div>
        <div style={{ display: activeTab === "architecture" ? "block" : "none" }}>
          <Architecture />
        </div>
      </main>
    </div>
  );
}
