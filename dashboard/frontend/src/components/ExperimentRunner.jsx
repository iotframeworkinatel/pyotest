import { useState, useEffect, useRef } from "react";
import { runExperiment, fetchExperimentStatus, startBatchRun, fetchBatchStatus } from "../api/experiments";
import {
  Play,
  Settings,
  Network,
  FileOutput,
  Gauge,
  Cpu,
  CheckCircle2,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Timer,
  Radar,
  Terminal,
  BrainCircuit,
  FlaskConical,
  BarChart3,
  Repeat,
  Hash,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Phases — detected from real scanner output keywords
// ---------------------------------------------------------------------------
const PHASES = [
  {
    id: "init",
    label: "Inicializando scanner",
    icon: Settings,
    // Matches immediately when experiment starts
    match: () => true,
  },
  {
    id: "discovery",
    label: "Descobrindo dispositivos (Nmap)",
    icon: Radar,
    // Scanner prints: "Running nmap scan..." or "Running Nmap on network"
    match: (output) =>
      /running nmap/i.test(output) || /nmap scan/i.test(output),
  },
  {
    id: "static_testing",
    label: "Testes estáticos de vulnerabilidade",
    icon: FlaskConical,
    // Scanner prints: "Starting static vulnerability tests..."
    match: (output) => /starting static vulnerability tests/i.test(output),
  },
  {
    id: "automl",
    label: "AutoML — Gerando testes adaptativos",
    icon: BrainCircuit,
    // Scanner prints: "Running AutoML to generate test cases"
    match: (output) => /running automl/i.test(output),
  },
  {
    id: "adaptive_testing",
    label: "Executando testes adaptativos",
    icon: Cpu,
    // Scanner prints: "Starting adaptive vulnerability tests..."
    match: (output) => /starting adaptive vulnerability tests/i.test(output),
  },
  {
    id: "report",
    label: "Gerando relatórios",
    icon: BarChart3,
    // Scanner prints: "Report saved as" or "IoT devices identified"
    match: (output) =>
      /report saved as/i.test(output) || /iot devices identified/i.test(output),
  },
];

/**
 * Detect the current phase by scanning all output lines for phase markers.
 * Returns the LAST (most advanced) phase whose marker was found.
 */
function detectPhase(scannerOutput, isAutoml) {
  if (!scannerOutput) return PHASES[0];

  let lastMatchedIdx = 0; // at minimum we're in "init"

  // Filter out automl phase if not in automl mode
  const activePhasesIds = isAutoml
    ? PHASES.map((p) => p.id)
    : PHASES.filter((p) => p.id !== "automl" && p.id !== "adaptive_testing").map(
        (p) => p.id
      );

  for (let i = 1; i < PHASES.length; i++) {
    const phase = PHASES[i];
    // Skip phases not active in this mode
    if (!activePhasesIds.includes(phase.id)) continue;
    if (phase.match(scannerOutput)) {
      lastMatchedIdx = i;
    }
  }

  return PHASES[lastMatchedIdx];
}

/**
 * Get only the phases relevant to the current mode.
 */
function getActivePhases(isAutoml) {
  if (isAutoml) return PHASES;
  return PHASES.filter((p) => p.id !== "automl" && p.id !== "adaptive_testing");
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function ExperimentRunner({ onExperimentComplete, refreshAll, onNavigateToStats }) {
  // -- Form state --
  const [params, setParams] = useState({
    mode: "automl",
    network: "172.20.0.0/27",
    output: "html",
    ports: "",
    verbose: false,
    test: false,
    automl: true,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [runMode, setRunMode] = useState("single"); // single | batch
  const [batchRuns, setBatchRuns] = useState(30);

  // -- Execution state --
  const [expStatus, setExpStatus] = useState(null);
  const [localStatus, setLocalStatus] = useState("idle"); // idle | running | completed | error | batch_running | batch_completed
  const [elapsedSec, setElapsedSec] = useState(0);
  const [scannerLines, setScannerLines] = useState([]);
  const [fullOutput, setFullOutput] = useState(""); // accumulated scanner output for phase detection
  const [detectedPhase, setDetectedPhase] = useState(PHASES[0]);
  const [devicesFound, setDevicesFound] = useState(null); // extracted from output
  const [batchProgress, setBatchProgress] = useState({ completed: 0, total: 0, experiments: [] });
  const pollRef = useRef(null);
  const timerRef = useRef(null);
  const terminalRef = useRef(null);
  const fullOutputRef = useRef("");
  const runningModeRef = useRef("automl");

  // -- Handlers --
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setParams((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  // Process scanner output: detect phase, extract info
  const processOutput = (rawOutput) => {
    if (!rawOutput) return;

    // Accumulate full output
    fullOutputRef.current += "\n" + rawOutput;
    setFullOutput(fullOutputRef.current);

    const lines = rawOutput.split("\n").filter(Boolean);
    setScannerLines(lines.slice(-15));

    // Detect phase from full accumulated output
    const isAutoml = runningModeRef.current === "automl";
    const phase = detectPhase(fullOutputRef.current, isAutoml);
    setDetectedPhase(phase);

    // Try to extract device count
    const deviceMatch = fullOutputRef.current.match(/(\d+)\s*devices?\s*found/i);
    if (deviceMatch) {
      setDevicesFound(parseInt(deviceMatch[1], 10));
    }
  };

  const startExperiment = async () => {
    try {
      setLocalStatus("running");
      setElapsedSec(0);
      setScannerLines([]);
      setFullOutput("");
      fullOutputRef.current = "";
      setDetectedPhase(PHASES[0]);
      setDevicesFound(null);
      runningModeRef.current = params.mode;

      const data = await runExperiment(params);
      if (data.status === "error") {
        setLocalStatus("error");
        setScannerLines([data.message || "Erro desconhecido"]);
        return;
      }

      // Start polling for status
      pollRef.current = setInterval(async () => {
        try {
          const st = await fetchExperimentStatus();
          setExpStatus(st);
          if (st.scanner_output) {
            processOutput(st.scanner_output);
          }
          if (st.status === "completed") {
            setLocalStatus("completed");
            clearInterval(pollRef.current);
            clearInterval(timerRef.current);
            if (refreshAll) refreshAll();
            if (onExperimentComplete) onExperimentComplete(st.experiment_id);
          } else if (st.status === "error") {
            setLocalStatus("error");
            clearInterval(pollRef.current);
            clearInterval(timerRef.current);
          }
        } catch {
          // ignore transient fetch errors
        }
      }, 2000);

      // Start elapsed timer
      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        setElapsedSec(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
    } catch (err) {
      setLocalStatus("error");
      setScannerLines(["Erro: " + err.message]);
    }
  };

  // -- Batch runner --
  const startBatch = async () => {
    try {
      setLocalStatus("batch_running");
      setElapsedSec(0);
      setScannerLines([]);
      setBatchProgress({ completed: 0, total: batchRuns, experiments: [] });
      runningModeRef.current = params.mode;

      const data = await startBatchRun({
        mode: params.mode,
        network: params.network,
        runs: batchRuns,
      });
      if (data.status === "error") {
        setLocalStatus("error");
        setScannerLines([data.message || "Erro desconhecido"]);
        return;
      }

      // Poll batch status
      pollRef.current = setInterval(async () => {
        try {
          const st = await fetchBatchStatus();
          setBatchProgress({
            completed: st.completed_runs || 0,
            total: st.total_runs || batchRuns,
            experiments: st.experiment_ids || [],
          });
          if (st.scanner_output) {
            const lines = st.scanner_output.split("\n").filter(Boolean);
            setScannerLines(lines.slice(-10));
          }
          if (st.status === "completed") {
            setLocalStatus("batch_completed");
            setBatchProgress({
              completed: st.total_runs,
              total: st.total_runs,
              experiments: st.experiment_ids || [],
            });
            clearInterval(pollRef.current);
            clearInterval(timerRef.current);
            if (refreshAll) refreshAll();
          } else if (st.status === "error") {
            setLocalStatus("error");
            setScannerLines([st.error || "Erro no lote"]);
            clearInterval(pollRef.current);
            clearInterval(timerRef.current);
          }
        } catch {}
      }, 3000);

      // Timer
      const startTime = Date.now();
      timerRef.current = setInterval(() => {
        setElapsedSec(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
    } catch (err) {
      setLocalStatus("error");
      setScannerLines(["Erro: " + err.message]);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [scannerLines]);

  // Check if already running on mount (single or batch)
  useEffect(() => {
    (async () => {
      try {
        // Check batch first
        const bst = await fetchBatchStatus();
        if (bst.status === "running") {
          setLocalStatus("batch_running");
          setElapsedSec(Math.floor(bst.elapsed_seconds || 0));
          setBatchProgress({
            completed: bst.completed_runs || 0,
            total: bst.total_runs || 0,
            experiments: bst.experiment_ids || [],
          });
          runningModeRef.current = bst.mode || "automl";
          // Resume polling
          pollRef.current = setInterval(async () => {
            try {
              const fresh = await fetchBatchStatus();
              setBatchProgress({
                completed: fresh.completed_runs || 0,
                total: fresh.total_runs || 0,
                experiments: fresh.experiment_ids || [],
              });
              setElapsedSec(Math.floor(fresh.elapsed_seconds || 0));
              if (fresh.scanner_output) {
                const lines = fresh.scanner_output.split("\n").filter(Boolean);
                setScannerLines(lines.slice(-10));
              }
              if (fresh.status === "completed") {
                setLocalStatus("batch_completed");
                clearInterval(pollRef.current);
                if (refreshAll) refreshAll();
              } else if (fresh.status === "error") {
                setLocalStatus("error");
                clearInterval(pollRef.current);
              }
            } catch {}
          }, 3000);
          const startTime = Date.now() - (bst.elapsed_seconds || 0) * 1000;
          timerRef.current = setInterval(() => {
            setElapsedSec(Math.floor((Date.now() - startTime) / 1000));
          }, 1000);
          return; // don't check single experiment
        }

        // Check single experiment
        const st = await fetchExperimentStatus();
        if (st.status === "running") {
          setLocalStatus("running");
          setExpStatus(st);
          setElapsedSec(Math.floor(st.elapsed_seconds || 0));
          if (st.command && st.command.includes("-aml")) {
            runningModeRef.current = "automl";
          } else {
            runningModeRef.current = "static";
          }
          if (st.scanner_output) {
            processOutput(st.scanner_output);
          }
          pollRef.current = setInterval(async () => {
            try {
              const fresh = await fetchExperimentStatus();
              setExpStatus(fresh);
              setElapsedSec(Math.floor(fresh.elapsed_seconds || 0));
              if (fresh.scanner_output) {
                processOutput(fresh.scanner_output);
              }
              if (fresh.status === "completed") {
                setLocalStatus("completed");
                clearInterval(pollRef.current);
                if (refreshAll) refreshAll();
                if (onExperimentComplete) onExperimentComplete(fresh.experiment_id);
              } else if (fresh.status === "error") {
                setLocalStatus("error");
                clearInterval(pollRef.current);
              }
            } catch {}
          }, 2000);
          const startTime = Date.now() - (st.elapsed_seconds || 0) * 1000;
          timerRef.current = setInterval(() => {
            setElapsedSec(Math.floor((Date.now() - startTime) / 1000));
          }, 1000);
        }
      } catch {}
    })();
  }, []);

  const resetToIdle = () => {
    setLocalStatus("idle");
    setExpStatus(null);
    setScannerLines([]);
    setFullOutput("");
    fullOutputRef.current = "";
    setElapsedSec(0);
    setDetectedPhase(PHASES[0]);
    setDevicesFound(null);
    setBatchProgress({ completed: 0, total: 0, experiments: [] });
  };

  const formatTime = (sec) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const isRunning = localStatus === "running";
  const isBatchRunning = localStatus === "batch_running";
  const isBatchCompleted = localStatus === "batch_completed";
  const isCompleted = localStatus === "completed";
  const isError = localStatus === "error";
  const isAutomlMode = params.mode === "automl" || runningModeRef.current === "automl";
  const activePhases = getActivePhases(isRunning ? runningModeRef.current === "automl" : isAutomlMode);

  // -------------------------------------------------------------------------
  // RENDER
  // -------------------------------------------------------------------------
  return (
    <div className="bg-white shadow-lg rounded-2xl overflow-hidden max-w-4xl mx-auto mb-8 border border-gray-200">
      {/* Header */}
      <div
        className={`px-6 py-4 flex items-center justify-between transition-colors duration-500 ${
          isRunning
            ? detectedPhase.id === "automl"
              ? "bg-gradient-to-r from-violet-600 to-purple-600"
              : "bg-gradient-to-r from-blue-600 to-indigo-600"
            : isBatchRunning
            ? "bg-gradient-to-r from-amber-600 to-orange-600"
            : isCompleted || isBatchCompleted
            ? "bg-gradient-to-r from-emerald-500 to-green-600"
            : isError
            ? "bg-gradient-to-r from-red-500 to-red-600"
            : "bg-gradient-to-r from-gray-700 to-gray-800"
        }`}
      >
        <div className="flex items-center gap-3 text-white">
          {isRunning || isBatchRunning ? (
            <Loader2 className="w-6 h-6 animate-spin" />
          ) : isCompleted || isBatchCompleted ? (
            <CheckCircle2 className="w-6 h-6" />
          ) : isError ? (
            <XCircle className="w-6 h-6" />
          ) : (
            <Gauge className="w-6 h-6" />
          )}
          <div>
            <h2 className="text-lg font-bold">
              {isBatchRunning
                ? `Lote em Execução — ${batchProgress.completed}/${batchProgress.total}`
                : isBatchCompleted
                ? "Lote Concluído"
                : isRunning
                ? "Experimento em Execução"
                : isCompleted
                ? "Experimento Concluído"
                : isError
                ? "Erro no Experimento"
                : "Configurar Experimento"}
            </h2>
            {isRunning && (
              <p className="text-sm text-white/80 mt-0.5">
                {detectedPhase.label}
              </p>
            )}
            {isBatchRunning && (
              <p className="text-sm text-white/80 mt-0.5">
                Experimento {batchProgress.completed + 1} de {batchProgress.total}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {isRunning && (
            <div className="flex items-center gap-2 text-white">
              {runningModeRef.current === "automl" && (
                <span className="text-xs bg-white/20 px-2.5 py-1 rounded-full font-semibold flex items-center gap-1.5">
                  <BrainCircuit className="w-3.5 h-3.5" />
                  AutoML
                </span>
              )}
              <Timer className="w-5 h-5" />
              <span className="font-mono text-lg font-semibold tabular-nums">
                {formatTime(elapsedSec)}
              </span>
            </div>
          )}
          {isBatchRunning && (
            <div className="flex items-center gap-2 text-white">
              <Repeat className="w-4 h-4" />
              <Timer className="w-5 h-5" />
              <span className="font-mono text-lg font-semibold tabular-nums">
                {formatTime(elapsedSec)}
              </span>
            </div>
          )}
          {(isCompleted || isError || isBatchCompleted) && (
            <button
              onClick={resetToIdle}
              className="px-4 py-1.5 rounded-lg bg-white/20 hover:bg-white/30 text-white text-sm font-medium transition"
            >
              Novo Experimento
            </button>
          )}
        </div>
      </div>

      {/* ===== BATCH RUNNING STATE ===== */}
      {isBatchRunning && (
        <div className="p-6 space-y-5">
          {/* Batch progress bar */}
          <div>
            <div className="flex justify-between text-sm text-gray-600 mb-2">
              <span>Progresso do Lote</span>
              <span className="font-semibold">
                {batchProgress.completed} / {batchProgress.total} concluídos
              </span>
            </div>
            <div className="w-full h-4 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-amber-500 to-orange-500 rounded-full transition-all duration-700 ease-out flex items-center justify-center"
                style={{
                  width: `${Math.max(
                    (batchProgress.completed / Math.max(batchProgress.total, 1)) * 100,
                    2
                  )}%`,
                }}
              >
                {batchProgress.completed > 0 && (
                  <span className="text-[10px] font-bold text-white">
                    {Math.round((batchProgress.completed / batchProgress.total) * 100)}%
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Info cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
              <p className="text-xs text-gray-500 mb-1">Modo</p>
              <p className="font-semibold text-gray-800 capitalize flex items-center gap-1.5">
                {runningModeRef.current === "automl" && <BrainCircuit className="w-4 h-4 text-violet-500" />}
                {runningModeRef.current === "automl" ? "AutoML" : "Static"}
              </p>
            </div>
            <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
              <p className="text-xs text-gray-500 mb-1">Total Execuções</p>
              <p className="font-semibold text-gray-800">{batchProgress.total}</p>
            </div>
            <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
              <p className="text-xs text-gray-500 mb-1">Tempo Decorrido</p>
              <p className="font-semibold text-gray-800 font-mono">{formatTime(elapsedSec)}</p>
            </div>
            <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
              <p className="text-xs text-gray-500 mb-1">Estimativa Restante</p>
              <p className="font-semibold text-gray-800 font-mono">
                {batchProgress.completed > 0
                  ? formatTime(
                      Math.round(
                        (elapsedSec / batchProgress.completed) *
                          (batchProgress.total - batchProgress.completed)
                      )
                    )
                  : "Calculando..."}
              </p>
            </div>
          </div>

          {/* Scanner output */}
          {scannerLines.length > 0 && (
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <Terminal className="w-4 h-4 text-amber-400" />
                <span className="text-xs font-semibold text-amber-400">
                  Execução {batchProgress.completed + 1} de {batchProgress.total}
                </span>
              </div>
              <div ref={terminalRef} className="font-mono text-xs text-gray-300 max-h-28 overflow-y-auto space-y-0.5">
                {scannerLines.map((line, i) => (
                  <div key={i} className="leading-relaxed">
                    <span className="text-gray-600 mr-2 select-none">$</span>
                    <span className={/automl|AutoML/i.test(line) ? "text-violet-400" : /found|completed/i.test(line) ? "text-green-400" : "text-gray-300"}>
                      {line}
                    </span>
                  </div>
                ))}
                <div className="inline-block w-2 h-4 bg-amber-400 animate-pulse ml-1" />
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===== BATCH COMPLETED STATE ===== */}
      {isBatchCompleted && (
        <div className="p-6 space-y-4">
          <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4">
            <CheckCircle2 className="w-8 h-8 text-emerald-500 flex-shrink-0" />
            <div className="flex-1">
              <p className="font-semibold text-emerald-700">
                Lote de {batchProgress.total} experimentos concluído!
              </p>
              <p className="text-sm text-emerald-600 mt-1">
                Tempo total: {formatTime(elapsedSec)} — {batchProgress.experiments.length} experimentos gerados
              </p>
            </div>
          </div>
          {onNavigateToStats && (
            <button
              onClick={onNavigateToStats}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-700 hover:to-purple-700 text-white font-semibold flex items-center justify-center gap-2 shadow-lg shadow-violet-200 transition-all"
            >
              <FlaskConical className="w-5 h-5" />
              Ver Análise Estatística
            </button>
          )}
        </div>
      )}

      {/* ===== RUNNING STATE ===== */}
      {isRunning && (
        <div className="p-6 space-y-5">
          {/* Phase indicators */}
          <div className={`grid grid-cols-2 gap-3 ${activePhases.length <= 4 ? "md:grid-cols-4" : "md:grid-cols-3"}`}>
            {activePhases.map((phase, idx) => {
              const PhaseIcon = phase.icon;
              const phaseIdx = activePhases.indexOf(phase);
              const currentIdx = activePhases.findIndex((p) => p.id === detectedPhase.id);
              const isCurrent = phase.id === detectedPhase.id;
              const isPast = currentIdx > phaseIdx;

              return (
                <div
                  key={phase.id}
                  className={`flex items-center gap-2.5 px-3 py-3 rounded-xl border-2 transition-all duration-500 ${
                    isCurrent
                      ? phase.id === "automl"
                        ? "border-violet-500 bg-violet-50 shadow-md shadow-violet-100"
                        : "border-blue-500 bg-blue-50 shadow-md shadow-blue-100"
                      : isPast
                      ? "border-emerald-400 bg-emerald-50"
                      : "border-gray-200 bg-gray-50 opacity-40"
                  }`}
                >
                  {isPast ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-500 flex-shrink-0" />
                  ) : (
                    <PhaseIcon
                      className={`w-5 h-5 flex-shrink-0 ${
                        isCurrent
                          ? phase.id === "automl"
                            ? "text-violet-600 animate-pulse"
                            : "text-blue-600 animate-pulse"
                          : "text-gray-400"
                      }`}
                    />
                  )}
                  <span
                    className={`text-xs font-medium leading-tight ${
                      isCurrent
                        ? phase.id === "automl"
                          ? "text-violet-700"
                          : "text-blue-700"
                        : isPast
                        ? "text-emerald-600"
                        : "text-gray-400"
                    }`}
                  >
                    {phase.label}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Progress bar — segments colored per phase */}
          <div className="w-full h-2.5 bg-gray-200 rounded-full overflow-hidden flex">
            {activePhases.map((phase, idx) => {
              const currentIdx = activePhases.findIndex((p) => p.id === detectedPhase.id);
              const segWidth = 100 / activePhases.length;
              const isFilled = idx < currentIdx;
              const isCurrent = idx === currentIdx;

              return (
                <div
                  key={phase.id}
                  className="h-full transition-all duration-700 ease-in-out"
                  style={{
                    width: `${segWidth}%`,
                    backgroundColor: isFilled
                      ? "#10b981"
                      : isCurrent
                      ? phase.id === "automl"
                        ? "#8b5cf6"
                        : "#3b82f6"
                      : "transparent",
                    opacity: isCurrent ? 0.7 : 1,
                  }}
                />
              );
            })}
          </div>

          {/* Execution info cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
              <p className="text-xs text-gray-500 mb-1">Modo</p>
              <p className="font-semibold text-gray-800 capitalize flex items-center gap-1.5">
                {runningModeRef.current === "automl" && (
                  <BrainCircuit className="w-4 h-4 text-violet-500" />
                )}
                {runningModeRef.current === "automl" ? "AutoML" : "Static"}
              </p>
            </div>
            <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
              <p className="text-xs text-gray-500 mb-1">Rede</p>
              <p className="font-semibold text-gray-800 font-mono text-sm">{params.network}</p>
            </div>
            <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
              <p className="text-xs text-gray-500 mb-1">Formato</p>
              <p className="font-semibold text-gray-800 uppercase">{params.output}</p>
            </div>
            <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
              <p className="text-xs text-gray-500 mb-1">Dispositivos</p>
              <p className="font-semibold text-gray-800">
                {devicesFound !== null ? (
                  <span className="flex items-center gap-1.5">
                    {devicesFound}
                    <span className="text-xs text-gray-400 font-normal">encontrados</span>
                  </span>
                ) : (
                  <span className="text-gray-400 text-sm">Buscando...</span>
                )}
              </p>
            </div>
          </div>

          {/* Scanner terminal output */}
          {scannerLines.length > 0 && (
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <Terminal className="w-4 h-4 text-green-400" />
                <span className="text-xs font-semibold text-green-400">Scanner Output</span>
                <span className="text-[10px] text-gray-500 ml-auto">
                  {formatTime(elapsedSec)} decorridos
                </span>
              </div>
              <div
                ref={terminalRef}
                className="font-mono text-xs text-gray-300 max-h-36 overflow-y-auto space-y-0.5"
              >
                {scannerLines.map((line, i) => (
                  <div key={i} className="leading-relaxed">
                    <span className="text-gray-600 mr-2 select-none">$</span>
                    <span
                      className={
                        /automl|AutoML/i.test(line)
                          ? "text-violet-400"
                          : /vuln|vulnerability/i.test(line)
                          ? "text-yellow-400"
                          : /error|erro|fail/i.test(line)
                          ? "text-red-400"
                          : /found|completed|saved/i.test(line)
                          ? "text-green-400"
                          : "text-gray-300"
                      }
                    >
                      {line}
                    </span>
                  </div>
                ))}
                <div className="inline-block w-2 h-4 bg-green-400 animate-pulse ml-1" />
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===== COMPLETED STATE ===== */}
      {isCompleted && (
        <div className="p-6">
          <div className="flex items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4">
            <CheckCircle2 className="w-8 h-8 text-emerald-500 flex-shrink-0" />
            <div>
              <p className="font-semibold text-emerald-700">
                Experimento finalizado com sucesso!
              </p>
              <p className="text-sm text-emerald-600 mt-1 flex flex-wrap items-center gap-2">
                <span>Tempo total: {formatTime(elapsedSec)}</span>
                {devicesFound !== null && (
                  <span className="bg-emerald-100 px-2 py-0.5 rounded text-xs">
                    {devicesFound} dispositivos
                  </span>
                )}
                {expStatus?.experiment_id && (
                  <span className="font-mono text-xs bg-emerald-100 px-2 py-0.5 rounded">
                    {expStatus.experiment_id}
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ===== ERROR STATE ===== */}
      {isError && (
        <div className="p-6">
          <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl px-5 py-4">
            <XCircle className="w-8 h-8 text-red-500 flex-shrink-0" />
            <div>
              <p className="font-semibold text-red-700">Erro na execução</p>
              <p className="text-sm text-red-600 mt-1">
                {expStatus?.error || "Erro desconhecido. Verifique os logs do scanner."}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ===== IDLE STATE — Config form ===== */}
      {localStatus === "idle" && (
        <div className="p-6 space-y-5">
          {/* Main settings row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Mode */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1.5">
                <Cpu className="w-4 h-4 text-blue-500" />
                Modo de Análise
              </label>
              <div className="flex gap-2">
                {[
                  { key: "static", label: "Static", desc: "Testes estáticos" },
                  { key: "automl", label: "AutoML", desc: "Testes adaptativos com ML", icon: BrainCircuit },
                ].map(({ key, label, desc, icon: ModeIcon }) => (
                  <button
                    key={key}
                    onClick={() => setParams((p) => ({ ...p, mode: key, automl: key === "automl" }))}
                    className={`flex-1 py-2.5 rounded-xl font-semibold text-sm transition-all flex flex-col items-center gap-0.5 ${
                      params.mode === key
                        ? key === "automl"
                          ? "bg-violet-600 text-white shadow-md shadow-violet-200"
                          : "bg-blue-600 text-white shadow-md shadow-blue-200"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      {ModeIcon && <ModeIcon className="w-4 h-4" />}
                      {label}
                    </span>
                    <span
                      className={`text-[10px] font-normal ${
                        params.mode === key ? "text-white/70" : "text-gray-400"
                      }`}
                    >
                      {desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Network */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1.5">
                <Network className="w-4 h-4 text-green-500" />
                Rede CIDR
              </label>
              <input
                type="text"
                name="network"
                value={params.network}
                onChange={handleChange}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
              />
            </div>

            {/* Output */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1.5">
                <FileOutput className="w-4 h-4 text-purple-500" />
                Formato de Saída
              </label>
              <div className="flex gap-2">
                {["html", "json", "csv"].map((fmt) => (
                  <button
                    key={fmt}
                    onClick={() => setParams((p) => ({ ...p, output: fmt }))}
                    className={`flex-1 py-2.5 rounded-xl font-semibold text-sm uppercase transition-all ${
                      params.output === fmt
                        ? "bg-purple-600 text-white shadow-md shadow-purple-200"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                    }`}
                  >
                    {fmt}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* AutoML mode info banner */}
          {params.mode === "automl" && (
            <div className="flex items-start gap-3 bg-violet-50 border border-violet-200 rounded-xl px-4 py-3">
              <BrainCircuit className="w-5 h-5 text-violet-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-violet-700">Modo AutoML ativado</p>
                <p className="text-xs text-violet-600 mt-0.5">
                  Além dos testes estáticos, o scanner usará Machine Learning para gerar e executar
                  testes adaptativos baseados nos dispositivos encontrados na rede.
                </p>
              </div>
            </div>
          )}

          {/* Advanced toggle */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition"
          >
            {showAdvanced ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
            Configurações avançadas
          </button>

          {showAdvanced && (
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-200 space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1.5 block">
                  Portas (separadas por vírgula)
                </label>
                <input
                  type="text"
                  name="ports"
                  value={params.ports}
                  onChange={handleChange}
                  placeholder="80, 443, 8080, 22, 21..."
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
                />
              </div>
              <div className="flex flex-wrap gap-6">
                {[
                  { name: "verbose", label: "Verbose", desc: "Mais detalhes no output" },
                  { name: "test", label: "Modo Teste", desc: "Apenas executar testes" },
                ].map(({ name, label, desc }) => (
                  <label key={name} className="flex items-start gap-2 cursor-pointer group">
                    <input
                      type="checkbox"
                      name={name}
                      checked={params[name]}
                      onChange={handleChange}
                      className="w-5 h-5 accent-blue-600 mt-0.5"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700 group-hover:text-blue-600 transition">
                        {label}
                      </span>
                      <p className="text-xs text-gray-400">{desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* RUN MODE TOGGLE */}
          <div className="flex rounded-xl overflow-hidden border border-gray-300">
            {[
              { key: "single", label: "Execução Única", icon: Play },
              { key: "batch", label: "Lote (Batch)", icon: Repeat },
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setRunMode(key)}
                className={`flex-1 py-2.5 text-sm font-medium flex items-center justify-center gap-2 transition-all ${
                  runMode === key
                    ? key === "batch"
                      ? "bg-amber-600 text-white"
                      : "bg-gray-800 text-white"
                    : "bg-gray-50 text-gray-600 hover:bg-gray-100"
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </div>

          {/* Batch config */}
          {runMode === "batch" && (
            <div className="flex items-center gap-4 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
              <Repeat className="w-5 h-5 text-amber-600 flex-shrink-0" />
              <div className="flex-1">
                <label className="text-sm font-medium text-amber-800 block mb-1">
                  Número de execuções
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min={2}
                    max={200}
                    value={batchRuns}
                    onChange={(e) => setBatchRuns(Math.max(2, parseInt(e.target.value) || 2))}
                    className="w-24 border border-amber-300 rounded-lg px-3 py-2 text-sm font-mono text-center focus:outline-none focus:ring-2 focus:ring-amber-400 bg-white"
                  />
                  <span className="text-xs text-amber-700">
                    Mínimo 30 recomendado para teste de hipótese (Teorema Central do Limite)
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* RUN BUTTON */}
          {runMode === "single" ? (
            <button
              onClick={startExperiment}
              className={`w-full py-4 rounded-xl font-bold text-lg flex items-center justify-center gap-3 shadow-lg transition-all active:scale-[0.99] text-white ${
                params.mode === "automl"
                  ? "bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-700 hover:to-purple-700 shadow-violet-200 hover:shadow-violet-300"
                  : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-blue-200 hover:shadow-blue-300"
              }`}
            >
              <Play className="w-6 h-6" />
              Iniciar Experimento
              {params.mode === "automl" && (
                <span className="text-sm font-normal opacity-80">(AutoML)</span>
              )}
            </button>
          ) : (
            <button
              onClick={startBatch}
              className="w-full py-4 rounded-xl font-bold text-lg flex items-center justify-center gap-3 shadow-lg transition-all active:scale-[0.99] text-white bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-700 hover:to-orange-700 shadow-amber-200 hover:shadow-amber-300"
            >
              <Repeat className="w-6 h-6" />
              Iniciar Lote de {batchRuns} Experimentos
            </button>
          )}
        </div>
      )}
    </div>
  );
}
