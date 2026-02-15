import { useState, useEffect } from "react";
import { fetchArchitectureMetadata } from "../api/experiments";
import SystemDiagram from "./architecture/SystemDiagram";
import ApiReference from "./architecture/ApiReference";
import ExperimentFlow from "./architecture/ExperimentFlow";
import TechStack from "./architecture/TechStack";
import {
  Network,
  BookOpen,
  GitBranch,
  Layers,
  Loader2,
  AlertCircle,
} from "lucide-react";

/* Tailwind JIT requires full class strings — no dynamic interpolation */
const SUB_TAB_ACTIVE = {
  emerald: "bg-emerald-50 text-emerald-700 border-emerald-200 shadow-sm",
  blue: "bg-blue-50 text-blue-700 border-blue-200 shadow-sm",
  purple: "bg-purple-50 text-purple-700 border-purple-200 shadow-sm",
  amber: "bg-amber-50 text-amber-700 border-amber-200 shadow-sm",
};

const SUB_TABS = [
  { id: "system", label: "System Overview", icon: Network, color: "emerald" },
  { id: "api", label: "API Reference", icon: BookOpen, color: "blue" },
  { id: "experiment", label: "Experiment Pipeline", icon: GitBranch, color: "purple" },
  { id: "techstack", label: "Tech Stack", icon: Layers, color: "amber" },
];

export default function Architecture() {
  const [activeSection, setActiveSection] = useState("system");
  const [metadata, setMetadata] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchArchitectureMetadata()
      .then((data) => {
        if (!cancelled) {
          setMetadata(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || "Failed to load architecture metadata");
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32 text-gray-400">
        <Loader2 className="w-6 h-6 animate-spin mr-3" />
        Loading architecture metadata...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-red-400 gap-3">
        <AlertCircle className="w-8 h-8" />
        <p className="text-sm">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="text-xs bg-red-50 text-red-600 px-4 py-2 rounded-lg hover:bg-red-100 transition"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-gray-800">Architecture</h2>
        <p className="text-sm text-gray-500 mt-1">
          System architecture, API reference, experiment pipeline, and technology stack
        </p>
      </div>

      {/* Sub-tab navigation */}
      <div className="flex gap-2 flex-wrap">
        {SUB_TABS.map(({ id, label, icon: Icon, color }) => (
          <button
            key={id}
            onClick={() => setActiveSection(id)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all border ${
              activeSection === id
                ? SUB_TAB_ACTIVE[color]
                : "bg-white text-gray-500 border-gray-200 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div>
        {activeSection === "system" && <SystemDiagram metadata={metadata} />}
        {activeSection === "api" && <ApiReference metadata={metadata} />}
        {activeSection === "experiment" && <ExperimentFlow metadata={metadata} />}
        {activeSection === "techstack" && <TechStack metadata={metadata} />}
      </div>
    </div>
  );
}
