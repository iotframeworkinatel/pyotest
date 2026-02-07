import { Filter, RefreshCw } from "lucide-react";

export default function ExperimentSelector({ experiments, selected, onSelect, onRefresh, loading }) {
  return (
    <div className="flex items-center gap-4 mb-6">
      <Filter className="w-5 h-5 text-gray-500" />
      <select
        value={selected || ""}
        onChange={(e) => onSelect(e.target.value || null)}
        className="border rounded-md px-3 py-2 text-sm bg-white"
      >
        <option value="">Todos os Experimentos</option>
        {experiments.map((exp) => (
          <option key={exp} value={exp}>
            {exp}
          </option>
        ))}
      </select>
      <button
        onClick={onRefresh}
        disabled={loading}
        className="flex items-center gap-2 px-3 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm disabled:opacity-50"
      >
        <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        Atualizar
      </button>
    </div>
  );
}
