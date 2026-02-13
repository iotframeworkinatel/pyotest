import { useState, useEffect, useRef, useMemo } from "react";
import { fetchLogs } from "../api/experiments";
import {
  Terminal,
  Search,
  Pause,
  Play,
  Trash2,
  Maximize2,
  Minimize2,
  Radio,
  ChevronDown,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Container color palette
// ---------------------------------------------------------------------------
const CONTAINER_COLORS = {
  scanner: { bg: "bg-blue-500", text: "text-blue-400", ring: "ring-blue-400" },
  http_: { bg: "bg-green-500", text: "text-green-400", ring: "ring-green-400" },
  ftp_: { bg: "bg-yellow-500", text: "text-yellow-400", ring: "ring-yellow-400" },
  ssh_: { bg: "bg-red-500", text: "text-red-400", ring: "ring-red-400" },
  telnet_: { bg: "bg-purple-500", text: "text-purple-400", ring: "ring-purple-400" },
  mqtt_: { bg: "bg-pink-500", text: "text-pink-400", ring: "ring-pink-400" },
  modbus_: { bg: "bg-orange-500", text: "text-orange-400", ring: "ring-orange-400" },
  coap_: { bg: "bg-teal-500", text: "text-teal-400", ring: "ring-teal-400" },
  dashboard: { bg: "bg-cyan-500", text: "text-cyan-400", ring: "ring-cyan-400" },
};

function getContainerColor(name) {
  for (const [prefix, colors] of Object.entries(CONTAINER_COLORS)) {
    if (name.startsWith(prefix)) return colors;
  }
  return { bg: "bg-gray-500", text: "text-gray-400", ring: "ring-gray-400" };
}

// ---------------------------------------------------------------------------
// Parse a log line with timestamp from Docker
// ---------------------------------------------------------------------------
function parseLogLine(raw) {
  // Docker timestamp format: 2024-01-15T12:34:56.789012345Z <message>
  const match = raw.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.\d+Z?\s*(.*)/);
  if (match) {
    const time = match[1].replace("T", " ").slice(11, 19); // HH:MM:SS
    return { time, message: match[2] };
  }
  return { time: null, message: raw };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function RealTimeLogs({ apiUrl }) {
  const [allLogs, setAllLogs] = useState({}); // { containerName: "raw text" }
  const [containerInfo, setContainerInfo] = useState([]); // [{name, status, image}]
  const [filter, setFilter] = useState("");
  const [selectedContainers, setSelectedContainers] = useState(new Set()); // empty = all
  const [isPaused, setIsPaused] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [viewMode, setViewMode] = useState("unified"); // unified | split | single
  const [singleContainer, setSingleContainer] = useState(null);
  const [showContainerPicker, setShowContainerPicker] = useState(false);
  const logEndRef = useRef(null);
  const pollRef = useRef(null);
  const pausedRef = useRef(false);

  // Keep pausedRef in sync with isPaused
  useEffect(() => {
    pausedRef.current = isPaused;
  }, [isPaused]);

  // -- Polling --
  const doFetch = async () => {
    if (pausedRef.current) return;
    try {
      const data = await fetchLogs(80);
      if (data.logs) setAllLogs(data.logs);
      if (data.container_info) setContainerInfo(data.container_info);
    } catch (err) {
      console.error("Erro ao buscar logs:", err);
    }
  };

  useEffect(() => {
    doFetch();
    pollRef.current = setInterval(doFetch, 3000);
    return () => clearInterval(pollRef.current);
  }, []);

  // Auto-scroll
  useEffect(() => {
    if (!isPaused && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [allLogs, isPaused]);

  // -- Derived data --
  const containerNames = useMemo(
    () => Object.keys(allLogs).sort(),
    [allLogs]
  );

  const filteredContainers = useMemo(() => {
    let names = containerNames;
    if (filter) {
      names = names.filter((n) => n.toLowerCase().includes(filter.toLowerCase()));
    }
    if (selectedContainers.size > 0) {
      names = names.filter((n) => selectedContainers.has(n));
    }
    return names;
  }, [containerNames, filter, selectedContainers]);

  // Build unified log stream: merge all container logs sorted by timestamp
  const unifiedLines = useMemo(() => {
    const lines = [];
    for (const name of filteredContainers) {
      const raw = allLogs[name] || "";
      const rawLines = raw.split("\n").filter(Boolean);
      for (const rl of rawLines) {
        const parsed = parseLogLine(rl);
        lines.push({ container: name, ...parsed, raw: rl });
      }
    }
    // Sort by raw timestamp if available (lexicographic works for ISO timestamps)
    lines.sort((a, b) => {
      if (!a.time && !b.time) return 0;
      if (!a.time) return -1;
      if (!b.time) return 1;
      return a.raw.localeCompare(b.raw);
    });
    return lines.slice(-300); // Keep last 300 lines
  }, [allLogs, filteredContainers]);

  // Toggle container selection
  const toggleContainer = (name) => {
    setSelectedContainers((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const clearFilter = () => {
    setSelectedContainers(new Set());
    setFilter("");
  };

  // -------------------------------------------------------------------------
  // RENDER
  // -------------------------------------------------------------------------
  return (
    <div
      className={`bg-gray-900 shadow-xl rounded-2xl overflow-hidden border border-gray-700 transition-all duration-300 ${
        isExpanded ? "fixed inset-4 z-50" : ""
      }`}
    >
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Radio className="w-4 h-4 text-red-400 animate-pulse" />
            <span className="text-sm font-bold text-white">Logs em Tempo Real</span>
          </div>
          <span className="text-xs text-gray-400 bg-gray-700 px-2 py-0.5 rounded-full">
            {containerNames.length} containers
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filtrar..."
              className="pl-8 pr-3 py-1.5 w-40 rounded-lg bg-gray-700 border border-gray-600 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Container picker dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowContainerPicker(!showContainerPicker)}
              className={`p-1.5 rounded-lg transition ${
                selectedContainers.size > 0
                  ? "bg-blue-600 text-white"
                  : "bg-gray-700 text-gray-300 hover:bg-gray-600"
              }`}
              title="Selecionar containers"
            >
              <ChevronDown className="w-4 h-4" />
            </button>
            {showContainerPicker && (
              <div className="absolute right-0 top-full mt-1 w-64 bg-gray-800 rounded-lg shadow-xl border border-gray-600 z-50 max-h-72 overflow-y-auto">
                <div className="p-2 border-b border-gray-700 flex justify-between">
                  <span className="text-xs text-gray-400 font-medium">Containers</span>
                  <button
                    onClick={clearFilter}
                    className="text-xs text-blue-400 hover:text-blue-300"
                  >
                    Mostrar todos
                  </button>
                </div>
                {containerNames.map((name) => {
                  const color = getContainerColor(name);
                  const isSelected =
                    selectedContainers.size === 0 || selectedContainers.has(name);
                  return (
                    <button
                      key={name}
                      onClick={() => toggleContainer(name)}
                      className={`w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-gray-700 transition text-sm ${
                        isSelected ? "opacity-100" : "opacity-40"
                      }`}
                    >
                      <span className={`w-2.5 h-2.5 rounded-full ${color.bg}`} />
                      <span className="text-gray-200 font-mono text-xs truncate">{name}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* View mode toggle */}
          <div className="flex rounded-lg overflow-hidden border border-gray-600">
            {[
              { mode: "unified", label: "Unificado" },
              { mode: "split", label: "Dividido" },
            ].map(({ mode, label }) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`px-2.5 py-1 text-xs font-medium transition ${
                  viewMode === mode
                    ? "bg-blue-600 text-white"
                    : "bg-gray-700 text-gray-400 hover:text-gray-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Pause/Play */}
          <button
            onClick={() => setIsPaused(!isPaused)}
            className={`p-1.5 rounded-lg transition ${
              isPaused
                ? "bg-yellow-600 text-white"
                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
            }`}
            title={isPaused ? "Retomar" : "Pausar"}
          >
            {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
          </button>

          {/* Expand/Collapse */}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1.5 rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 transition"
            title={isExpanded ? "Minimizar" : "Expandir"}
          >
            {isExpanded ? (
              <Minimize2 className="w-4 h-4" />
            ) : (
              <Maximize2 className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      {/* Paused banner */}
      {isPaused && (
        <div className="bg-yellow-600/20 border-b border-yellow-600/30 px-4 py-1.5 flex items-center gap-2">
          <Pause className="w-3.5 h-3.5 text-yellow-400" />
          <span className="text-xs text-yellow-300 font-medium">
            Auto-refresh pausado — clique em Play para retomar
          </span>
        </div>
      )}

      {/* Log content area */}
      <div
        className={`overflow-y-auto ${
          isExpanded ? "h-[calc(100vh-12rem)]" : "h-[28rem]"
        }`}
      >
        {viewMode === "unified" ? (
          /* ===== UNIFIED VIEW ===== */
          <div className="p-3 space-y-0">
            {unifiedLines.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-gray-500">
                <Terminal className="w-8 h-8 mb-2" />
                <p className="text-sm">Nenhum log disponível ainda.</p>
              </div>
            ) : (
              unifiedLines.map((line, i) => {
                const color = getContainerColor(line.container);
                return (
                  <div
                    key={i}
                    className="flex items-start gap-2 py-0.5 hover:bg-gray-800/50 px-2 rounded group"
                  >
                    {line.time && (
                      <span className="text-[10px] text-gray-600 font-mono mt-0.5 flex-shrink-0 w-16 tabular-nums">
                        {line.time}
                      </span>
                    )}
                    <span
                      className={`text-[10px] font-mono ${color.text} mt-0.5 flex-shrink-0 w-28 truncate`}
                      title={line.container}
                    >
                      {line.container}
                    </span>
                    <span className="text-xs text-gray-300 font-mono leading-relaxed break-all">
                      {line.message}
                    </span>
                  </div>
                );
              })
            )}
            <div ref={logEndRef} />
          </div>
        ) : (
          /* ===== SPLIT VIEW ===== */
          <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-gray-700">
            {filteredContainers.map((name) => {
              const color = getContainerColor(name);
              const raw = allLogs[name] || "";
              const lines = raw.split("\n").filter(Boolean).slice(-30);
              const info = containerInfo.find((c) => c.name === name);

              return (
                <div
                  key={name}
                  className="bg-gray-900 flex flex-col min-h-[14rem] max-h-[20rem]"
                >
                  {/* Container header */}
                  <div className="flex items-center justify-between px-3 py-2 bg-gray-800/50 border-b border-gray-700/50">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${color.bg}`} />
                      <span className={`text-xs font-mono font-semibold ${color.text}`}>
                        {name}
                      </span>
                    </div>
                    {info && (
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                          info.status === "running"
                            ? "bg-green-900/50 text-green-400"
                            : "bg-gray-700 text-gray-400"
                        }`}
                      >
                        {info.status}
                      </span>
                    )}
                  </div>
                  {/* Lines */}
                  <div className="flex-1 overflow-y-auto p-2 space-y-0">
                    {lines.map((rl, i) => {
                      const parsed = parseLogLine(rl);
                      return (
                        <div key={i} className="flex items-start gap-1.5 py-0.5">
                          {parsed.time && (
                            <span className="text-[10px] text-gray-600 font-mono flex-shrink-0 tabular-nums">
                              {parsed.time}
                            </span>
                          )}
                          <span className="text-[11px] text-gray-300 font-mono leading-relaxed break-all">
                            {parsed.message}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-t border-gray-700 text-[11px] text-gray-500">
        <span>
          {filteredContainers.length} de {containerNames.length} containers
          {selectedContainers.size > 0 && " (filtrado)"}
        </span>
        <span>
          {viewMode === "unified"
            ? `${unifiedLines.length} linhas`
            : `${filteredContainers.length} painéis`}
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isPaused ? "bg-yellow-400" : "bg-green-400 animate-pulse"
            }`}
          />
          {isPaused ? "Pausado" : "Atualizando a cada 3s"}
        </span>
      </div>
    </div>
  );
}
