import { useState, useEffect, useRef, useCallback } from "react";
import {
  ListChecks,
  ChevronRight,
  ChevronLeft,
  Download,
  Play,
  Loader2,
  Star,
  Zap,
  Filter,
  ArrowUpDown,
  BrainCircuit,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  Info,
  Calendar,
  Hash,
  Cpu,
  RefreshCw,
  FileJson,
  FileCode,
  FileText,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Layers,
  Server,
  ChevronDown,
  ChevronUp,
  X,
  Sparkles,
  Repeat,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SEVERITY_COLORS = {
  critical: { bg: "bg-red-100", text: "text-red-700", border: "border-red-300", dot: "bg-red-500" },
  high: { bg: "bg-orange-100", text: "text-orange-700", border: "border-orange-300", dot: "bg-orange-500" },
  medium: { bg: "bg-yellow-100", text: "text-yellow-700", border: "border-yellow-300", dot: "bg-yellow-500" },
  low: { bg: "bg-blue-100", text: "text-blue-700", border: "border-blue-300", dot: "bg-blue-500" },
  info: { bg: "bg-gray-100", text: "text-gray-600", border: "border-gray-300", dot: "bg-gray-400" },
};

function getRiskScoreColor(score) {
  if (score === null || score === undefined) return { bg: "bg-gray-100", text: "text-gray-500" };
  if (score >= 0.7) return { bg: "bg-red-100", text: "text-red-700" };
  if (score >= 0.5) return { bg: "bg-orange-100", text: "text-orange-700" };
  if (score >= 0.3) return { bg: "bg-yellow-100", text: "text-yellow-700" };
  return { bg: "bg-green-100", text: "text-green-700" };
}

function getSeverityIcon(severity) {
  switch (severity) {
    case "critical":
      return ShieldAlert;
    case "high":
      return ShieldAlert;
    case "medium":
      return Shield;
    case "low":
      return ShieldCheck;
    case "info":
      return ShieldQuestion;
    default:
      return Shield;
  }
}

function formatDate(dateStr) {
  if (!dateStr) return "N/A";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

// ---------------------------------------------------------------------------
// SeverityBadge
// ---------------------------------------------------------------------------
function SeverityBadge({ severity }) {
  const key = (severity || "info").toLowerCase();
  const colors = SEVERITY_COLORS[key] || SEVERITY_COLORS.info;
  const Icon = getSeverityIcon(key);
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${colors.bg} ${colors.text} ${colors.border} border`}
    >
      <Icon className="w-3 h-3" />
      {key.charAt(0).toUpperCase() + key.slice(1)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// RiskScoreBadge
// ---------------------------------------------------------------------------
function RiskScoreBadge({ score }) {
  const colors = getRiskScoreColor(score);
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono font-semibold ${colors.bg} ${colors.text}`}
    >
      {score !== null && score !== undefined ? score.toFixed(2) : "N/A"}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ProtocolBadge
// ---------------------------------------------------------------------------
function ProtocolBadge({ protocol }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
      {protocol}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
export default function TestSuites({ apiUrl, onRunSuite, visible = true }) {
  // ---- Suite list state ----
  const [suites, setSuites] = useState([]);
  const [suitesLoading, setSuitesLoading] = useState(true);
  const [suitesError, setSuitesError] = useState(null);

  // ---- Selected suite state ----
  const [selectedSuiteId, setSelectedSuiteId] = useState(null);
  const [suiteDetail, setSuiteDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  // ---- Filters & sorting ----
  const [sortField, setSortField] = useState("risk_score");
  const [sortDirection, setSortDirection] = useState("desc");
  const [filterProtocol, setFilterProtocol] = useState("");
  const [filterSeverity, setFilterSeverity] = useState("");
  const [filterRecommended, setFilterRecommended] = useState("");
  const [showFilters, setShowFilters] = useState(false);

  // ---- Run state ----
  const [runStatus, setRunStatus] = useState(null); // null | "running" | "completed" | "error"
  const [runProgress, setRunProgress] = useState(0);
  const [runMessage, setRunMessage] = useState("");
  const runPollRef = useRef(null);

  // ---- Export state ----
  const [exportLoading, setExportLoading] = useState(null); // null | "json" | "yaml" | "python"

  // ---- ML Insights state ----
  const [mlStatus, setMlStatus] = useState(null);
  const [mlLoading, setMlLoading] = useState(true);
  const [mlError, setMlError] = useState(null);
  const [showFeatures, setShowFeatures] = useState(false);
  const [showLeaderboard, setShowLeaderboard] = useState(false);
  const [retrainStatus, setRetrainStatus] = useState("idle"); // idle | training | completed | error
  const [retrainMessage, setRetrainMessage] = useState(null);
  const [retrainStartedAt, setRetrainStartedAt] = useState(null);
  const [retrainElapsed, setRetrainElapsed] = useState(0);
  const retrainPollRef = useRef(null);
  const retrainTimerRef = useRef(null);

  // ---- Auto-Train Loop state ----
  const [loopIterations, setLoopIterations] = useState(3);
  const [loopTrainEveryN, setLoopTrainEveryN] = useState(0); // 0 = train only at end
  const [loopStatus, setLoopStatus] = useState(null); // null | "running" | "completed" | "error" | "cancelled"
  const [loopPhase, setLoopPhase] = useState("idle");
  const [loopCurrentIter, setLoopCurrentIter] = useState(0);
  const [loopTotalIter, setLoopTotalIter] = useState(0);

  // ---- Simulation state ----
  const [simMode, setSimMode] = useState("deterministic");
  const [simSeed, setSimSeed] = useState(42);
  const [simProfiles, setSimProfiles] = useState([]);
  const [loopMetrics, setLoopMetrics] = useState([]);
  const [loopError, setLoopError] = useState(null);
  const loopPollRef = useRef(null);
  const resumingRef = useRef(false); // true while resume-on-mount is setting state
  const selectedSuiteIdRef = useRef(null); // ref for use in async callbacks

  // ---- AutoML Framework state ----
  const [automlTool, setAutomlTool] = useState("h2o");
  const [availableFrameworks, setAvailableFrameworks] = useState(["h2o"]);

  const stopLoopPolling = useCallback(() => {
    if (loopPollRef.current) {
      clearInterval(loopPollRef.current);
      loopPollRef.current = null;
    }
  }, []);

  const stopRetrainPolling = useCallback(() => {
    if (retrainPollRef.current) {
      clearInterval(retrainPollRef.current);
      retrainPollRef.current = null;
    }
    if (retrainTimerRef.current) {
      clearInterval(retrainTimerRef.current);
      retrainTimerRef.current = null;
    }
  }, []);

  // =========================================================================
  // Fetch suite list
  // =========================================================================
  const fetchSuites = useCallback(async () => {
    setSuitesLoading(true);
    setSuitesError(null);
    try {
      const res = await fetch(`${apiUrl}/api/suites`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSuites(Array.isArray(data) ? data : data.suites || []);
    } catch (err) {
      setSuitesError(err.message);
    } finally {
      setSuitesLoading(false);
    }
  }, [apiUrl]);

  const hasMountedRef = useRef(false);

  useEffect(() => {
    fetchSuites().finally(() => { hasMountedRef.current = true; });
    // Fetch simulation profiles once on mount
    fetch(`${apiUrl}/api/simulation/profiles`)
      .then(r => r.json())
      .then(d => setSimProfiles(d.profiles || []))
      .catch(() => {});
    // Fetch available AutoML frameworks
    fetch(`${apiUrl}/api/automl/frameworks`)
      .then(r => r.json())
      .then(d => {
        const fws = (d.frameworks || []).map(f => f.name);
        if (fws.length > 0) setAvailableFrameworks(fws);
      })
      .catch(() => {});
  }, [fetchSuites]);

  // Auto-refresh suite list when the tab becomes visible
  useEffect(() => {
    if (visible && hasMountedRef.current) {
      fetchSuites();
      if (selectedSuiteIdRef.current) fetchSuiteDetail(selectedSuiteIdRef.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // =========================================================================
  // Fetch suite detail
  // =========================================================================
  const fetchSuiteDetail = useCallback(
    async (suiteId) => {
      setDetailLoading(true);
      setDetailError(null);
      setSuiteDetail(null);
      try {
        const res = await fetch(`${apiUrl}/api/suites/${suiteId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setSuiteDetail(data);
      } catch (err) {
        setDetailError(err.message);
      } finally {
        setDetailLoading(false);
      }
    },
    [apiUrl]
  );

  useEffect(() => {
    selectedSuiteIdRef.current = selectedSuiteId;
    if (selectedSuiteId) {
      fetchSuiteDetail(selectedSuiteId);
      // Skip state reset if we're resuming a running task on mount
      if (!resumingRef.current) {
        // Reset run state when selecting a new suite
        setRunStatus(null);
        setRunProgress(0);
        setRunMessage("");
        if (runPollRef.current) {
          clearInterval(runPollRef.current);
          runPollRef.current = null;
        }
        // Reset loop state
        setLoopStatus(null);
        setLoopMetrics([]);
        setLoopError(null);
        stopLoopPolling();
      }
    }
  }, [selectedSuiteId, fetchSuiteDetail]);

  // =========================================================================
  // Fetch ML status
  // =========================================================================
  const fetchMlStatus = useCallback(async () => {
    setMlLoading(true);
    setMlError(null);
    try {
      const res = await fetch(`${apiUrl}/api/ml/status?automl_tool=${automlTool}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMlStatus(data);
    } catch (err) {
      setMlError(err.message);
    } finally {
      setMlLoading(false);
    }
  }, [apiUrl, automlTool]);

  useEffect(() => {
    fetchMlStatus();
  }, [fetchMlStatus]);

  // =========================================================================
  // Cleanup polling on unmount
  // =========================================================================
  useEffect(() => {
    return () => {
      if (runPollRef.current) {
        clearInterval(runPollRef.current);
      }
      stopRetrainPolling();
      stopLoopPolling();
    };
  }, [stopRetrainPolling, stopLoopPolling]);

  // =========================================================================
  // Export handlers
  // =========================================================================
  const handleExport = async (format) => {
    if (!selectedSuiteId) return;
    setExportLoading(format);
    try {
      const res = await fetch(
        `${apiUrl}/api/suites/${selectedSuiteId}/export?format=${format}`
      );
      if (!res.ok) throw new Error(`Export failed: HTTP ${res.status}`);
      const blob = await res.blob();

      const extensions = { json: "json", yaml: "yaml", python: "py" };
      const ext = extensions[format] || format;
      const filename = `suite_${selectedSuiteId}.${ext}`;

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export error:", err);
    } finally {
      setExportLoading(null);
    }
  };

  // =========================================================================
  // Run suite handler
  // =========================================================================
  const handleRunSuite = async () => {
    if (!selectedSuiteId) return;
    setRunStatus("running");
    setRunProgress(0);
    setRunMessage("Starting suite run...");

    try {
      const res = await fetch(`${apiUrl}/api/suites/${selectedSuiteId}/run`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Run failed: HTTP ${res.status}`);

      // Start polling for status
      runPollRef.current = setInterval(async () => {
        try {
          const statusRes = await fetch(
            `${apiUrl}/api/suites/${selectedSuiteId}/run/status`
          );
          if (!statusRes.ok) return;
          const statusData = await statusRes.json();

          setRunProgress(statusData.progress || 0);
          setRunMessage(statusData.message || statusData.status || "");

          if (statusData.status === "completed") {
            setRunStatus("completed");
            setRunProgress(100);
            setRunMessage("Suite run completed. Auto-training ML model...");
            clearInterval(runPollRef.current);
            runPollRef.current = null;
            if (onRunSuite) onRunSuite(selectedSuiteId, statusData);
            // Refresh suite list & detail to show updated metadata
            fetchSuites();
            if (selectedSuiteId) fetchSuiteDetail(selectedSuiteId);
            // Auto-retrain starts server-side — begin polling training status
            startTrainingPoll();
          } else if (statusData.status === "error" || statusData.status === "failed") {
            setRunStatus("error");
            setRunMessage(statusData.error || statusData.message || "Run failed.");
            clearInterval(runPollRef.current);
            runPollRef.current = null;
          }
        } catch {
          // Ignore transient fetch errors during polling
        }
      }, 2000);
    } catch (err) {
      setRunStatus("error");
      setRunMessage(err.message);
    }
  };

  // =========================================================================
  // Start polling training status (used after suite run + manual retrain)
  // =========================================================================
  const startTrainingPoll = useCallback((resumeStartedAt) => {
    stopRetrainPolling();
    setRetrainStatus("training");

    // If resuming, compute elapsed from the original backend start time
    const startTime = resumeStartedAt ? new Date(resumeStartedAt).getTime() : Date.now();
    setRetrainElapsed(Math.floor((Date.now() - startTime) / 1000));

    retrainTimerRef.current = setInterval(() => {
      setRetrainElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    retrainPollRef.current = setInterval(async () => {
      try {
        const statusRes = await fetch(`${apiUrl}/api/ml/retrain/status`);
        if (!statusRes.ok) return;
        const statusData = await statusRes.json();

        if (statusData.status === "completed") {
          stopRetrainPolling();
          setRetrainStatus("completed");
          const aucText = statusData.auc ? ` AUC: ${statusData.auc}` : "";
          const rowsText = statusData.training_rows ? ` (${statusData.training_rows} samples)` : "";
          setRetrainMessage({
            type: "success",
            text: `Model trained successfully.${aucText}${rowsText} Suite risk scores updated.`,
          });
          fetchMlStatus();
          // Refresh suite data — scores were auto-updated by the backend
          fetchSuites();
          if (selectedSuiteIdRef.current) fetchSuiteDetail(selectedSuiteIdRef.current);
        } else if (statusData.status === "error") {
          stopRetrainPolling();
          setRetrainStatus("error");
          setRetrainMessage({
            type: "error",
            text: statusData.error || "Training failed",
          });
        }
      } catch {
        // Ignore transient errors
      }
    }, 3000);
  }, [apiUrl, stopRetrainPolling, fetchMlStatus, fetchSuites, fetchSuiteDetail]);

  // =========================================================================
  // Resume training poll on mount if training is already in progress
  // =========================================================================
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${apiUrl}/api/ml/retrain/status`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (data.status === "training" && !cancelled) {
          startTrainingPoll(data.started_at);
        }
      } catch {
        // Ignore — backend may be unreachable
      }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, startTrainingPoll]);

  // =========================================================================
  // Resume run & loop polling on mount if something is already active
  // =========================================================================
  useEffect(() => {
    let cancelled = false;

    (async () => {
      // Check for active single-run
      try {
        const runRes = await fetch(`${apiUrl}/api/run/active`);
        if (!runRes.ok || cancelled) return;
        const runData = await runRes.json();
        if (runData.status === "running" && !cancelled) {
          const suiteId = runData.suite_id;
          if (suiteId) {
            resumingRef.current = true;
            setSelectedSuiteId(suiteId);
            setRunStatus("running");
            setRunProgress(runData.progress || 0);
            setRunMessage("Resuming run monitoring...");
            // Clear the flag after React processes the state updates
            setTimeout(() => { resumingRef.current = false; }, 100);

            runPollRef.current = setInterval(async () => {
              try {
                const sr = await fetch(`${apiUrl}/api/suites/${suiteId}/run/status`);
                if (!sr.ok) return;
                const sd = await sr.json();
                setRunProgress(sd.progress || 0);
                setRunMessage(sd.message || sd.status || "");
                if (sd.status === "completed") {
                  setRunStatus("completed");
                  setRunProgress(100);
                  setRunMessage("Suite run completed. Auto-training ML model...");
                  clearInterval(runPollRef.current);
                  runPollRef.current = null;
                  fetchSuites();
                  startTrainingPoll();
                } else if (sd.status === "error" || sd.status === "failed") {
                  setRunStatus("error");
                  setRunMessage(sd.error || sd.message || "Run failed.");
                  clearInterval(runPollRef.current);
                  runPollRef.current = null;
                }
              } catch { /* ignore */ }
            }, 2000);
          }
        }
      } catch { /* ignore */ }

      // Check for active loop
      try {
        const loopRes = await fetch(`${apiUrl}/api/loop/active`);
        if (!loopRes.ok || cancelled) return;
        const loopData = await loopRes.json();
        if (loopData.status === "running" && !cancelled) {
          const suiteId = loopData.suite_id;
          if (suiteId) {
            resumingRef.current = true;
            setSelectedSuiteId(suiteId);
            setLoopStatus("running");
            setLoopCurrentIter(loopData.current_iteration || 0);
            setLoopTotalIter(loopData.total_iterations || 0);
            setLoopPhase(loopData.phase || "idle");
            setLoopMetrics(loopData.iterations || []);
            setTimeout(() => { resumingRef.current = false; }, 100);

            loopPollRef.current = setInterval(async () => {
              try {
                const sr = await fetch(`${apiUrl}/api/suites/${suiteId}/train-loop/status`);
                if (!sr.ok) return;
                const s = await sr.json();
                setLoopCurrentIter(s.current_iteration || 0);
                setLoopTotalIter(s.total_iterations || 0);
                setLoopPhase(s.phase || "idle");
                setLoopMetrics(s.iterations || []);
                if (s.status === "completed" || s.status === "error" || s.status === "cancelled") {
                  setLoopStatus(s.status);
                  setLoopError(s.error || null);
                  stopLoopPolling();
                  fetchMlStatus();
                  fetchSuites();
                  if (suiteId) fetchSuiteDetail(suiteId);
                }
              } catch { /* ignore */ }
            }, 3000);
          }
        }
      } catch { /* ignore */ }
    })();

    return () => { cancelled = true; };
  }, [apiUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  // =========================================================================
  // Retrain ML model (with polling)
  // =========================================================================
  const handleRetrain = async () => {
    setRetrainMessage(null);
    try {
      const res = await fetch(`${apiUrl}/api/ml/retrain?automl_tool=${automlTool}`, { method: "POST" });
      if (!res.ok) throw new Error(`Retrain failed: HTTP ${res.status}`);
      const data = await res.json();

      if (data.status === "already_training") {
        setRetrainMessage({ type: "info", text: data.message });
        // Still poll for the existing training to finish
      }

      startTrainingPoll();
    } catch (err) {
      stopRetrainPolling();
      setRetrainStatus("error");
      setRetrainMessage({ type: "error", text: err.message });
    }
  };

  // =========================================================================
  // Auto-Train Loop handlers
  // =========================================================================
  const handleStartTrainLoop = async () => {
    if (!selectedSuiteId) return;
    setLoopStatus("running");
    setLoopPhase("idle");
    setLoopCurrentIter(0);
    setLoopTotalIter(loopIterations);
    setLoopMetrics([]);
    setLoopError(null);

    try {
      const res = await fetch(`${apiUrl}/api/suites/${selectedSuiteId}/train-loop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          iterations: loopIterations,
          train_every_n: loopTrainEveryN,
          simulation_mode: simMode,
          simulation_seed: simSeed,
          automl_tool: automlTool,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.status === "error") {
        setLoopStatus("error");
        setLoopError(data.message);
        return;
      }

      // Start polling loop status
      loopPollRef.current = setInterval(async () => {
        try {
          const statusRes = await fetch(
            `${apiUrl}/api/suites/${selectedSuiteId}/train-loop/status`
          );
          if (!statusRes.ok) return;
          const s = await statusRes.json();

          setLoopCurrentIter(s.current_iteration || 0);
          setLoopTotalIter(s.total_iterations || 0);
          setLoopPhase(s.phase || "idle");
          setLoopMetrics(s.iterations || []);

          if (s.status === "completed" || s.status === "error" || s.status === "cancelled") {
            setLoopStatus(s.status);
            setLoopError(s.error || null);
            stopLoopPolling();
            fetchMlStatus();
            // Refresh suite list & detail to show updated metadata
            fetchSuites();
            if (selectedSuiteId) fetchSuiteDetail(selectedSuiteId);
          }
        } catch {
          // ignore transient errors
        }
      }, 3000);
    } catch (err) {
      setLoopStatus("error");
      setLoopError(err.message);
    }
  };

  const handleCancelTrainLoop = async () => {
    try {
      await fetch(`${apiUrl}/api/suites/${selectedSuiteId}/train-loop/cancel`, {
        method: "POST",
      });
    } catch (err) {
      console.error("Cancel loop error:", err);
    }
  };

  // =========================================================================
  // Sorting & filtering logic for test cases
  // =========================================================================
  const getFilteredAndSortedTests = () => {
    if (!suiteDetail || !suiteDetail.test_cases) return [];

    let tests = [...suiteDetail.test_cases];

    // Apply filters
    if (filterProtocol) {
      tests = tests.filter(
        (t) => (t.protocol || "").toLowerCase() === filterProtocol.toLowerCase()
      );
    }
    if (filterSeverity) {
      tests = tests.filter(
        (t) => (t.severity || "").toLowerCase() === filterSeverity.toLowerCase()
      );
    }
    if (filterRecommended === "true") {
      tests = tests.filter((t) => t.is_recommended === true);
    } else if (filterRecommended === "false") {
      tests = tests.filter((t) => !t.is_recommended);
    }

    // Apply sorting
    tests.sort((a, b) => {
      let valA = a[sortField];
      let valB = b[sortField];

      // Handle nulls
      if (valA === null || valA === undefined) valA = sortDirection === "desc" ? -Infinity : Infinity;
      if (valB === null || valB === undefined) valB = sortDirection === "desc" ? -Infinity : Infinity;

      // String comparison
      if (typeof valA === "string") {
        return sortDirection === "desc"
          ? valB.localeCompare(valA)
          : valA.localeCompare(valB);
      }

      // Number comparison
      return sortDirection === "desc" ? valB - valA : valA - valB;
    });

    return tests;
  };

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  // Collect unique protocols and severities from current suite for filter dropdowns
  const uniqueProtocols = suiteDetail?.test_cases
    ? [...new Set(suiteDetail.test_cases.map((t) => t.protocol).filter(Boolean))]
    : [];
  const uniqueSeverities = suiteDetail?.test_cases
    ? [...new Set(suiteDetail.test_cases.map((t) => t.severity).filter(Boolean))]
    : [];

  const filteredTests = getFilteredAndSortedTests();

  // =========================================================================
  // RENDER
  // =========================================================================
  return (
    <div className="max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold mb-6 text-center flex items-center justify-center gap-2">
        <ListChecks className="w-7 h-7 text-indigo-600" />
        Test Suites
      </h2>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* ================================================================
            LEFT: Suite List + ML Insights
            ================================================================ */}
        <div className="lg:col-span-1 space-y-6">
          {/* Suite List */}
          <div className="bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
            <div className="px-4 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Layers className="w-4 h-4" />
                Generated Suites
              </h3>
              <button
                onClick={fetchSuites}
                className="p-1 rounded-lg hover:bg-white/20 transition text-white"
                title="Refresh suites"
              >
                <RefreshCw className={`w-4 h-4 ${suitesLoading ? "animate-spin" : ""}`} />
              </button>
            </div>

            <div className="max-h-[500px] overflow-y-auto">
              {suitesLoading && suites.length === 0 ? (
                <div className="flex items-center justify-center py-12 text-gray-400">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" />
                  Loading suites...
                </div>
              ) : suitesError ? (
                <div className="p-4 text-center">
                  <XCircle className="w-6 h-6 text-red-400 mx-auto mb-2" />
                  <p className="text-sm text-red-600">{suitesError}</p>
                  <button
                    onClick={fetchSuites}
                    className="mt-2 text-xs text-indigo-600 hover:underline"
                  >
                    Retry
                  </button>
                </div>
              ) : suites.length === 0 ? (
                <div className="p-6 text-center text-gray-400">
                  <ListChecks className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No test suites generated yet.</p>
                  <p className="text-xs mt-1">Run an experiment to generate suites.</p>
                </div>
              ) : (
                suites.map((suite) => {
                  const isSelected = selectedSuiteId === (suite.id || suite.suite_id);
                  const suiteId = suite.id || suite.suite_id;

                  return (
                    <button
                      key={suiteId}
                      onClick={() =>
                        setSelectedSuiteId(isSelected ? null : suiteId)
                      }
                      className={`w-full text-left px-4 py-3 border-b border-gray-100 transition-all hover:bg-gray-50 ${
                        isSelected
                          ? "bg-indigo-50 border-l-4 border-l-indigo-500"
                          : "border-l-4 border-l-transparent"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p
                            className={`text-sm font-semibold truncate ${
                              isSelected ? "text-indigo-700" : "text-gray-800"
                            }`}
                          >
                            {suite.name || `Suite #${suiteId}`}
                          </p>
                          <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {formatDate(suite.created_at || suite.created)}
                          </p>
                        </div>
                        <ChevronRight
                          className={`w-4 h-4 flex-shrink-0 mt-1 transition-transform ${
                            isSelected ? "rotate-90 text-indigo-500" : "text-gray-300"
                          }`}
                        />
                      </div>

                      {/* Suite stats row */}
                      <div className="flex flex-wrap items-center gap-1.5 mt-2">
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-600">
                          <Hash className="w-2.5 h-2.5" />
                          {suite.test_count || suite.total_tests || 0} tests
                        </span>
                        {(suite.recommended_count > 0) && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-600">
                            <Zap className="w-2.5 h-2.5" />
                            {suite.recommended_count} recommended
                          </span>
                        )}
                        {(suite.device_count !== undefined && suite.device_count !== null) && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-600">
                            <Server className="w-2.5 h-2.5" />
                            {suite.device_count} devices
                          </span>
                        )}
                        {(suite.enhancement_count > 0) && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-violet-50 text-violet-600">
                            <Sparkles className="w-2.5 h-2.5" />
                            Enhanced &times;{suite.enhancement_count}
                          </span>
                        )}
                        {suite.automl_tool && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-600">
                            {suite.automl_tool === "h2o" ? "H2O" :
                             suite.automl_tool === "autogluon" ? "AutoGluon" :
                             suite.automl_tool === "pycaret" ? "PyCaret" :
                             suite.automl_tool === "tpot" ? "TPOT" :
                             suite.automl_tool === "autosklearn" ? "auto-sklearn" : suite.automl_tool}
                          </span>
                        )}
                      </div>

                      {/* Protocol badges */}
                      {suite.protocols && suite.protocols.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {suite.protocols.slice(0, 4).map((proto) => (
                            <span
                              key={proto}
                              className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-50 text-indigo-600"
                            >
                              {proto}
                            </span>
                          ))}
                          {suite.protocols.length > 4 && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] text-gray-400">
                              +{suite.protocols.length - 4}
                            </span>
                          )}
                        </div>
                      )}
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* ================================================================
              ML Insights Panel
              ================================================================ */}
          {(() => {
            const isTraining = retrainStatus === "training" || loopPhase === "training";
            return (
          <div className={`bg-white rounded-2xl shadow-md border overflow-hidden transition-all duration-500 ${isTraining ? "border-violet-400 ring-2 ring-violet-300/50" : "border-gray-200"}`}>
            <div className={`px-4 py-3 flex items-center gap-2 transition-all duration-500 ${isTraining ? "bg-gradient-to-r from-violet-600 via-fuchsia-500 to-violet-600 bg-[length:200%_100%] animate-[shimmer_2s_ease-in-out_infinite]" : "bg-gradient-to-r from-violet-600 to-fuchsia-600"}`}>
              <BrainCircuit className={`w-4 h-4 text-white ${isTraining ? "animate-pulse" : ""}`} />
              <h3 className="text-sm font-bold text-white">ML Insights</h3>
              <span className="text-[10px] font-medium text-white/80 bg-white/15 px-1.5 py-0.5 rounded">
                {automlTool === "h2o" ? "H2O" :
                 automlTool === "autogluon" ? "AutoGluon" :
                 automlTool === "pycaret" ? "PyCaret" :
                 automlTool === "tpot" ? "TPOT" :
                 automlTool === "autosklearn" ? "auto-sklearn" : automlTool}
              </span>
              {isTraining && (
                <span className="ml-auto inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-white/20 text-white backdrop-blur-sm">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  TRAINING
                </span>
              )}
            </div>

            <div className="p-4 space-y-3">
              {mlLoading ? (
                <div className="flex items-center justify-center py-6 text-gray-400">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" />
                  Loading ML status...
                </div>
              ) : mlError ? (
                <div className="text-center py-4">
                  <XCircle className="w-5 h-5 text-red-400 mx-auto mb-1" />
                  <p className="text-xs text-red-500">{mlError}</p>
                  <button
                    onClick={fetchMlStatus}
                    className="mt-1 text-xs text-violet-600 hover:underline"
                  >
                    Retry
                  </button>
                </div>
              ) : mlStatus ? (
                <>
                  {/* ── Model status badge ── */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-500">Model Status</span>
                    {isTraining ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-violet-100 text-violet-700 animate-pulse">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Training...
                      </span>
                    ) : mlStatus.trained || mlStatus.status === "trained" ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">
                        <CheckCircle2 className="w-3 h-3" />
                        Trained
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
                        <AlertTriangle className="w-3 h-3" />
                        Untrained
                      </span>
                    )}
                  </div>

                  {/* ── Leader model algorithm ── */}
                  {mlStatus.leader_algo && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-500">Leader Model</span>
                      <span className="text-xs font-semibold text-violet-700 bg-violet-50 px-2 py-0.5 rounded-full capitalize">
                        {mlStatus.leader_algo}
                      </span>
                    </div>
                  )}

                  {/* ── AUC Score (prefer cv_auc fallback) ── */}
                  {(() => {
                    const auc = mlStatus.auc ?? mlStatus.cv_auc;
                    return auc != null ? (
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-500">AUC Score</span>
                        <span
                          className={`text-sm font-mono font-bold ${
                            auc >= 0.8
                              ? "text-emerald-600"
                              : auc >= 0.6
                              ? "text-yellow-600"
                              : "text-red-600"
                          }`}
                        >
                          {typeof auc === "number" ? auc.toFixed(4) : auc}
                        </span>
                      </div>
                    ) : null;
                  })()}

                  {/* ── Training data & models evaluated ── */}
                  {(() => {
                    const rows = mlStatus.training_rows ?? mlStatus.training_data_size;
                    return rows != null ? (
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-500">Training Data</span>
                        <span className="text-sm font-semibold text-gray-700">
                          {rows.toLocaleString()} samples
                        </span>
                      </div>
                    ) : null;
                  })()}

                  {mlStatus.total_models_trained != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-500">Models Evaluated</span>
                      <span className="text-sm font-semibold text-gray-700">
                        {mlStatus.total_models_trained}
                      </span>
                    </div>
                  )}

                  {/* ── Feature Importance (collapsible, top 8) ── */}
                  {mlStatus.feature_importance?.length > 0 && (
                    <div className="border border-gray-100 rounded-xl overflow-hidden">
                      <button
                        onClick={() => setShowFeatures(prev => !prev)}
                        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors"
                      >
                        <span className="text-xs font-semibold text-gray-600 flex items-center gap-1.5">
                          <Layers className="w-3.5 h-3.5" />
                          Feature Importance
                        </span>
                        {showFeatures ? (
                          <ChevronUp className="w-3.5 h-3.5 text-gray-400" />
                        ) : (
                          <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                        )}
                      </button>
                      {showFeatures && (
                        <div className="px-3 py-2 space-y-1.5">
                          {mlStatus.feature_importance
                            .filter(f => f.scaled_importance > 0)
                            .slice(0, 8)
                            .map((f, i) => (
                              <div key={i} className="space-y-0.5">
                                <div className="flex items-center justify-between">
                                  <span className="text-[10px] text-gray-500 font-mono truncate max-w-[140px]" title={f.variable}>
                                    {f.variable}
                                  </span>
                                  <span className="text-[10px] text-gray-400 font-mono">
                                    {(Number(f.percentage || 0) * 100).toFixed(1)}%
                                  </span>
                                </div>
                                <div className="w-full bg-gray-100 rounded-full h-1">
                                  <div
                                    className="h-full bg-gradient-to-r from-violet-400 to-fuchsia-400 rounded-full transition-all"
                                    style={{ width: `${(Number(f.scaled_importance || 0) * 100).toFixed(1)}%` }}
                                  />
                                </div>
                              </div>
                            ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* ── Leaderboard (collapsible, top 5) ── */}
                  {mlStatus.leaderboard?.length > 0 && (
                    <div className="border border-gray-100 rounded-xl overflow-hidden">
                      <button
                        onClick={() => setShowLeaderboard(prev => !prev)}
                        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors"
                      >
                        <span className="text-xs font-semibold text-gray-600 flex items-center gap-1.5">
                          <Star className="w-3.5 h-3.5" />
                          Model Leaderboard
                        </span>
                        {showLeaderboard ? (
                          <ChevronUp className="w-3.5 h-3.5 text-gray-400" />
                        ) : (
                          <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                        )}
                      </button>
                      {showLeaderboard && (
                        <div className="px-2 py-2 space-y-1">
                          {mlStatus.leaderboard.slice(0, 5).map((m, i) => {
                            // Extract short algo name from model_id like "DeepLearning_1_AutoML_..." → "DeepLearning"
                            const algoName = typeof m.model_id === "string"
                              ? m.model_id.split("_").slice(0, m.model_id.startsWith("GBM_grid") ? 2 : 1).join("_")
                              : `Model ${i + 1}`;
                            return (
                              <div
                                key={i}
                                className={`flex items-center justify-between px-2 py-1.5 rounded-lg ${
                                  i === 0 ? "bg-violet-50 border border-violet-200" : "bg-gray-50"
                                }`}
                              >
                                <div className="flex items-center gap-1.5">
                                  <span className={`text-[10px] font-bold w-4 text-center ${i === 0 ? "text-violet-600" : "text-gray-400"}`}>
                                    {i === 0 ? "★" : `#${i + 1}`}
                                  </span>
                                  <span className={`text-[11px] font-mono truncate max-w-[100px] ${i === 0 ? "text-violet-700 font-semibold" : "text-gray-600"}`}>
                                    {algoName}
                                  </span>
                                </div>
                                <span className={`text-[11px] font-mono font-bold ${
                                  m.auc >= 0.8 ? "text-emerald-600" : m.auc >= 0.6 ? "text-yellow-600" : "text-red-600"
                                }`}>
                                  {typeof m.auc === "number" ? m.auc.toFixed(4) : "—"}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}

                  {/* ── Untrained message ── */}
                  {!mlStatus.trained && mlStatus.status !== "trained" && (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 mt-2">
                      <p className="text-xs text-amber-700 flex items-center gap-1.5">
                        <Info className="w-3.5 h-3.5 flex-shrink-0" />
                        Run tests to train ML model
                      </p>
                    </div>
                  )}

                  {/* ── Training in progress ── */}
                  {retrainStatus === "training" && (
                    <div className="bg-violet-50 border border-violet-200 rounded-xl px-3 py-3 mt-2 space-y-2">
                      <div className="flex items-center gap-2">
                        <Loader2 className="w-4 h-4 animate-spin text-violet-600" />
                        <span className="text-xs font-semibold text-violet-700">
                          Training in progress...
                        </span>
                      </div>
                      <div className="w-full bg-violet-100 rounded-full h-1.5 overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-violet-500 to-fuchsia-500 rounded-full animate-pulse" style={{ width: "100%" }} />
                      </div>
                      <p className="text-[10px] text-violet-500 font-mono text-center">
                        Elapsed: {Math.floor(retrainElapsed / 60)}:{String(retrainElapsed % 60).padStart(2, "0")}
                      </p>
                    </div>
                  )}

                  {/* ── Retrain button ── */}
                  <button
                    onClick={handleRetrain}
                    disabled={retrainStatus === "training"}
                    className="w-full mt-2 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-700 hover:to-fuchsia-700 text-white text-sm font-semibold flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {retrainStatus === "training" ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Training...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        Retrain Model
                      </>
                    )}
                  </button>

                  {/* ── Retrain result message ── */}
                  {retrainMessage && retrainStatus !== "training" && (
                    <div
                      className={`rounded-lg px-3 py-2 text-xs flex items-start gap-1.5 ${
                        retrainMessage.type === "success"
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : retrainMessage.type === "info"
                          ? "bg-blue-50 text-blue-700 border border-blue-200"
                          : "bg-red-50 text-red-700 border border-red-200"
                      }`}
                    >
                      {retrainMessage.type === "success" ? (
                        <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                      ) : retrainMessage.type === "info" ? (
                        <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                      )}
                      {retrainMessage.text}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-gray-400 text-center py-4">
                  No ML status available.
                </p>
              )}
            </div>
          </div>
            );
          })()}
        </div>

        {/* ================================================================
            RIGHT: Suite Detail + Actions
            ================================================================ */}
        <div className="lg:col-span-3 space-y-6">
          {!selectedSuiteId ? (
            /* Placeholder when no suite is selected */
            <div className="bg-white rounded-2xl shadow-md border border-gray-200 flex flex-col items-center justify-center py-24 text-gray-400">
              <Layers className="w-12 h-12 mb-3 opacity-30" />
              <p className="text-lg font-semibold text-gray-500">Select a Test Suite</p>
              <p className="text-sm mt-1">
                Choose a suite from the list to view details and export options.
              </p>
            </div>
          ) : detailLoading ? (
            <div className="bg-white rounded-2xl shadow-md border border-gray-200 flex items-center justify-center py-24 text-gray-400">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              Loading suite details...
            </div>
          ) : detailError ? (
            <div className="bg-white rounded-2xl shadow-md border border-gray-200 p-8 text-center">
              <XCircle className="w-8 h-8 text-red-400 mx-auto mb-2" />
              <p className="text-red-600 font-medium">Failed to load suite</p>
              <p className="text-sm text-red-500 mt-1">{detailError}</p>
              <button
                onClick={() => fetchSuiteDetail(selectedSuiteId)}
                className="mt-3 text-sm text-indigo-600 hover:underline"
              >
                Retry
              </button>
            </div>
          ) : suiteDetail ? (
            <>
              {/* ============================================================
                  Suite Header + Metadata
                  ============================================================ */}
              <div className="bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
                <div className="px-6 py-4 bg-gradient-to-r from-gray-700 to-gray-800 flex items-center justify-between">
                  <div className="flex items-center gap-3 text-white">
                    <button
                      onClick={() => setSelectedSuiteId(null)}
                      className="p-1 rounded-lg hover:bg-white/20 transition"
                      title="Back to suite list"
                    >
                      <ChevronLeft className="w-5 h-5" />
                    </button>
                    <div>
                      <h3 className="text-lg font-bold">
                        {suiteDetail.name || `Suite #${selectedSuiteId}`}
                      </h3>
                      <p className="text-xs text-white/70 mt-0.5 flex items-center gap-2">
                        <Calendar className="w-3 h-3" />
                        {formatDate(suiteDetail.created_at || suiteDetail.created)}
                        {suiteDetail.test_cases && (
                          <span className="bg-white/20 px-1.5 py-0.5 rounded text-[10px]">
                            {suiteDetail.test_cases.length} tests
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedSuiteId(null)}
                    className="p-1 rounded-lg hover:bg-white/20 transition text-white"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Suite metadata bar */}
                <div className="px-6 py-3 bg-gray-50 border-b border-gray-200 flex flex-wrap items-center gap-4 text-xs text-gray-600">
                  {suiteDetail.generation_params && (
                    <span className="flex items-center gap-1">
                      <Cpu className="w-3.5 h-3.5 text-blue-500" />
                      <strong>Params:</strong>{" "}
                      {typeof suiteDetail.generation_params === "string"
                        ? suiteDetail.generation_params
                        : JSON.stringify(suiteDetail.generation_params)}
                    </span>
                  )}
                  {suiteDetail.metadata?.automl_tool && (
                    <span className="flex items-center gap-1">
                      <Cpu className="w-3.5 h-3.5 text-blue-500" />
                      <strong>Scored with:</strong>{" "}
                      {suiteDetail.metadata.automl_tool === "h2o" ? "H2O" :
                       suiteDetail.metadata.automl_tool === "autogluon" ? "AutoGluon" :
                       suiteDetail.metadata.automl_tool === "pycaret" ? "PyCaret" :
                       suiteDetail.metadata.automl_tool === "tpot" ? "TPOT" :
                       suiteDetail.metadata.automl_tool === "autosklearn" ? "auto-sklearn" :
                       suiteDetail.metadata.automl_tool}
                    </span>
                  )}
                  {suiteDetail.recommended_count > 0 && (
                    <span className="flex items-center gap-1">
                      <Zap className="w-3.5 h-3.5 text-amber-500" />
                      <strong>ML Recommended:</strong>{" "}
                      {suiteDetail.recommended_count} tests
                    </span>
                  )}
                  {suiteDetail.protocols && suiteDetail.protocols.length > 0 && (
                    <span className="flex items-center gap-1">
                      <Layers className="w-3.5 h-3.5 text-indigo-500" />
                      <strong>Protocols:</strong> {suiteDetail.protocols.join(", ")}
                    </span>
                  )}
                </div>
              </div>

              {/* ============================================================
                  Action Buttons
                  ============================================================ */}
              <div className="flex flex-wrap items-center gap-3">
                {/* Export JSON */}
                <button
                  onClick={() => handleExport("json")}
                  disabled={exportLoading !== null}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border border-gray-200 shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {exportLoading === "json" ? (
                    <Loader2 className="w-4 h-4 animate-spin text-amber-500" />
                  ) : (
                    <FileJson className="w-4 h-4 text-amber-500" />
                  )}
                  Export JSON
                </button>

                {/* Export YAML */}
                <button
                  onClick={() => handleExport("yaml")}
                  disabled={exportLoading !== null}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border border-gray-200 shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {exportLoading === "yaml" ? (
                    <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                  ) : (
                    <FileText className="w-4 h-4 text-blue-500" />
                  )}
                  Export YAML
                </button>

                {/* Export Python */}
                <button
                  onClick={() => handleExport("python")}
                  disabled={exportLoading !== null}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white border border-gray-200 shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {exportLoading === "python" ? (
                    <Loader2 className="w-4 h-4 animate-spin text-green-500" />
                  ) : (
                    <FileCode className="w-4 h-4 text-green-500" />
                  )}
                  Export Python
                </button>

                {/* Spacer */}
                <div className="flex-1" />

                {/* Run Suite */}
                <button
                  onClick={handleRunSuite}
                  disabled={runStatus === "running" || loopStatus === "running"}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-700 hover:to-green-700 text-white text-sm font-semibold shadow-lg shadow-emerald-200 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {runStatus === "running" ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4" />
                  )}
                  {runStatus === "running" ? "Running..." : "Run Suite"}
                </button>
              </div>

              {/* ============================================================
                  Auto-Train Loop Controls
                  ============================================================ */}
              <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-gray-200">
                <div className="flex items-center gap-2">
                  <label className="text-sm text-gray-600 font-medium">Auto-Train:</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={loopIterations}
                    onChange={(e) => setLoopIterations(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
                    disabled={loopStatus === "running"}
                    className="w-16 border border-gray-300 rounded-lg px-2 py-1.5 text-sm text-center focus:ring-2 focus:ring-violet-400 focus:outline-none disabled:opacity-50"
                  />
                  <span className="text-xs text-gray-400">iterations</span>
                </div>

                {/* Train Every N */}
                <div className="flex items-center gap-2">
                  <label className="text-sm text-gray-600 font-medium">Train every:</label>
                  <input
                    type="number"
                    min={0}
                    max={loopIterations}
                    value={loopTrainEveryN}
                    onChange={(e) => setLoopTrainEveryN(Math.max(0, Math.min(loopIterations, parseInt(e.target.value) || 0)))}
                    disabled={loopStatus === "running"}
                    className="w-16 border border-gray-300 rounded-lg px-2 py-1.5 text-sm text-center focus:ring-2 focus:ring-violet-400 focus:outline-none disabled:opacity-50"
                  />
                  <span className="text-xs text-gray-400" title="0 = train only after last iteration, N = train every Nth iteration + last">
                    {loopTrainEveryN === 0 ? "end only" : loopTrainEveryN === 1 ? "every iter" : `every ${loopTrainEveryN}`}
                  </span>
                </div>

                {/* Simulation Mode */}
                <div className="flex items-center gap-2">
                  <label className="text-sm text-gray-600 font-medium">Simulation:</label>
                  <select
                    value={simMode}
                    onChange={(e) => setSimMode(e.target.value)}
                    disabled={loopStatus === "running"}
                    title={
                      simProfiles.find((p) => p.name === simMode)?.description || ""
                    }
                    className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-violet-400 focus:outline-none disabled:opacity-50"
                  >
                    {simProfiles.length > 0 ? (
                      simProfiles.map((p) => (
                        <option key={p.name} value={p.name}>
                          {p.name.charAt(0).toUpperCase() + p.name.slice(1)}
                        </option>
                      ))
                    ) : (
                      <>
                        <option value="deterministic">Deterministic</option>
                        <option value="easy">Easy</option>
                        <option value="medium">Medium</option>
                        <option value="hard">Hard</option>
                        <option value="realistic">Realistic</option>
                      </>
                    )}
                  </select>
                </div>

                {/* Simulation Seed */}
                {simMode !== "deterministic" && (
                  <div className="flex items-center gap-1">
                    <label className="text-xs text-gray-400">Seed:</label>
                    <input
                      type="number"
                      min={1}
                      max={999999}
                      value={simSeed}
                      onChange={(e) => setSimSeed(Math.max(1, parseInt(e.target.value) || 42))}
                      disabled={loopStatus === "running"}
                      className="w-20 border border-gray-300 rounded-lg px-2 py-1.5 text-sm text-center focus:ring-2 focus:ring-violet-400 focus:outline-none disabled:opacity-50"
                    />
                  </div>
                )}

                {/* AutoML Framework */}
                <div className="flex items-center gap-2">
                  <label className="text-sm text-gray-600 font-medium">AutoML:</label>
                  <select
                    value={automlTool}
                    onChange={(e) => setAutomlTool(e.target.value)}
                    disabled={loopStatus === "running"}
                    className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-violet-400 focus:outline-none disabled:opacity-50"
                  >
                    {availableFrameworks.map((fw) => (
                      <option key={fw} value={fw}>
                        {fw === "h2o" ? "H2O" :
                         fw === "autogluon" ? "AutoGluon" :
                         fw === "pycaret" ? "PyCaret" :
                         fw === "tpot" ? "TPOT" :
                         fw === "autosklearn" ? "auto-sklearn" : fw}
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  onClick={handleStartTrainLoop}
                  disabled={loopStatus === "running" || runStatus === "running"}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-700 hover:to-fuchsia-700 text-white text-sm font-semibold shadow-lg shadow-violet-200 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loopStatus === "running" ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Repeat className="w-4 h-4" />
                  )}
                  {loopStatus === "running" ? "Loop Running..." : "Auto-Train Loop"}
                </button>

                {loopStatus === "running" && (
                  <button
                    onClick={handleCancelTrainLoop}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-red-100 text-red-700 text-sm font-semibold hover:bg-red-200 transition-all"
                  >
                    <X className="w-4 h-4" />
                    Cancel
                  </button>
                )}
              </div>

              {/* ============================================================
                  Run Progress
                  ============================================================ */}
              {runStatus && (
                <div
                  className={`rounded-2xl border p-4 ${
                    runStatus === "running"
                      ? "bg-blue-50 border-blue-200"
                      : runStatus === "completed"
                      ? "bg-emerald-50 border-emerald-200"
                      : "bg-red-50 border-red-200"
                  }`}
                >
                  <div className="flex items-center gap-3 mb-3">
                    {runStatus === "running" ? (
                      <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
                    ) : runStatus === "completed" ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-500" />
                    )}
                    <span
                      className={`text-sm font-semibold ${
                        runStatus === "running"
                          ? "text-blue-700"
                          : runStatus === "completed"
                          ? "text-emerald-700"
                          : "text-red-700"
                      }`}
                    >
                      {runStatus === "running"
                        ? "Suite Running"
                        : runStatus === "completed"
                        ? "Run Completed"
                        : "Run Failed"}
                    </span>
                    {runStatus !== "running" && (
                      <button
                        onClick={() => {
                          setRunStatus(null);
                          setRunProgress(0);
                          setRunMessage("");
                        }}
                        className="ml-auto p-1 rounded hover:bg-black/5 transition"
                      >
                        <X className="w-4 h-4 text-gray-400" />
                      </button>
                    )}
                  </div>

                  {/* Progress bar */}
                  {runStatus === "running" && (
                    <div className="w-full h-3 bg-white/80 rounded-full overflow-hidden mb-2">
                      <div
                        className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-500 ease-out"
                        style={{ width: `${Math.max(runProgress, 2)}%` }}
                      />
                    </div>
                  )}

                  {runMessage && (
                    <p
                      className={`text-xs ${
                        runStatus === "running"
                          ? "text-blue-600"
                          : runStatus === "completed"
                          ? "text-emerald-600"
                          : "text-red-600"
                      }`}
                    >
                      {runMessage}
                      {runStatus === "running" && runProgress > 0 && (
                        <span className="ml-2 font-mono font-semibold">
                          {Math.round(runProgress)}%
                        </span>
                      )}
                    </p>
                  )}
                </div>
              )}

              {/* ============================================================
                  Auto-Train Loop Progress
                  ============================================================ */}
              {loopStatus && (
                <div
                  className={`rounded-2xl border p-4 ${
                    loopStatus === "running"
                      ? "bg-violet-50 border-violet-200"
                      : loopStatus === "completed"
                      ? "bg-emerald-50 border-emerald-200"
                      : loopStatus === "cancelled"
                      ? "bg-amber-50 border-amber-200"
                      : "bg-red-50 border-red-200"
                  }`}
                >
                  {/* Header */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      {loopStatus === "running" ? (
                        <Loader2 className="w-5 h-5 text-violet-500 animate-spin" />
                      ) : loopStatus === "completed" ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                      ) : loopStatus === "cancelled" ? (
                        <AlertTriangle className="w-5 h-5 text-amber-500" />
                      ) : (
                        <XCircle className="w-5 h-5 text-red-500" />
                      )}
                      <span className="text-sm font-semibold">
                        Auto-Train Loop
                        {loopStatus !== "running" && (
                          <span className="ml-1 text-xs font-normal text-gray-500">
                            ({loopStatus})
                          </span>
                        )}
                        {simMode !== "deterministic" && (
                          <span className="ml-2 px-1.5 py-0.5 text-[10px] font-medium bg-violet-100 text-violet-700 rounded">
                            sim: {simMode}
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono font-bold">
                        Iter {loopCurrentIter}/{loopTotalIter}
                      </span>
                      {loopStatus !== "running" && (
                        <button
                          onClick={() => { setLoopStatus(null); setLoopMetrics([]); setLoopError(null); }}
                          className="p-1 rounded hover:bg-black/5 transition"
                        >
                          <X className="w-4 h-4 text-gray-400" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Phase indicator */}
                  {loopStatus === "running" && (
                    <p className="text-xs text-violet-600 mb-2">
                      {loopPhase === "simulation_prepare"
                        ? "Simulation: preparing environment..."
                        : loopPhase === "running"
                        ? "Executing tests..."
                        : loopPhase === "training"
                        ? "Training ML model..."
                        : loopPhase === "scoring"
                        ? "Scoring suite with updated model..."
                        : loopPhase === "simulation_restore"
                        ? "Simulation: restoring containers..."
                        : loopPhase === "between_iterations"
                        ? "Preparing next iteration..."
                        : "Starting..."}
                    </p>
                  )}

                  {/* Progress bar */}
                  <div className="w-full h-3 bg-white/80 rounded-full overflow-hidden mb-3">
                    <div
                      className="h-full bg-gradient-to-r from-violet-500 to-fuchsia-500 rounded-full transition-all duration-500"
                      style={{
                        width: `${
                          loopTotalIter > 0
                            ? ((loopStatus === "running" ? loopCurrentIter - 0.5 : loopCurrentIter) / loopTotalIter) * 100
                            : 0
                        }%`,
                      }}
                    />
                  </div>

                  {/* Error */}
                  {loopError && (
                    <p className="text-xs text-red-600 mb-2">{loopError}</p>
                  )}

                  {/* Per-iteration metrics table */}
                  {loopMetrics.length > 0 && (
                    <div className="mt-3 border-t border-gray-200/60 pt-3">
                      <p className="text-xs font-semibold text-gray-600 mb-2">Per-Iteration Metrics</p>
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-gray-500 border-b">
                              <th className="py-1 text-left">#</th>
                              <th className="py-1 text-right">Tests</th>
                              <th className="py-1 text-right">Vulns</th>
                              <th className="py-1 text-right">Det. Rate</th>
                              <th className="py-1 text-right">AUC</th>
                              <th className="py-1 text-right">Rows</th>
                              <th className="py-1 text-right">Recommended</th>
                              {simMode !== "deterministic" && (
                                <th className="py-1 text-right">Sim Events</th>
                              )}
                            </tr>
                          </thead>
                          <tbody>
                            {loopMetrics.map((m) => (
                              <tr key={m.iteration} className="border-b border-gray-100">
                                <td className="py-1 font-mono">{m.iteration}</td>
                                <td className="py-1 text-right">{m.tests_executed}</td>
                                <td className="py-1 text-right">{m.vulns_detected}</td>
                                <td className="py-1 text-right font-mono">
                                  {(m.detection_rate * 100).toFixed(1)}%
                                </td>
                                <td className="py-1 text-right font-mono">
                                  {m.retrain_auc != null ? m.retrain_auc.toFixed(4) : "---"}
                                </td>
                                <td className="py-1 text-right">{m.retrain_rows || "---"}</td>
                                <td className="py-1 text-right">
                                  {m.recommended_tests != null
                                    ? `${m.recommended_tests}/${m.scored_tests}`
                                    : "---"}
                                </td>
                                {simMode !== "deterministic" && (
                                  <td className="py-1 text-right font-mono text-violet-600">
                                    {m.simulation_actions != null ? m.simulation_actions : "---"}
                                  </td>
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ============================================================
                  Filters
                  ============================================================ */}
              <div className="bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                  <button
                    onClick={() => setShowFilters(!showFilters)}
                    className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-800 transition"
                  >
                    <Filter className="w-4 h-4" />
                    Filters & Sort
                    {showFilters ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </button>
                  <span className="text-xs text-gray-400">
                    {filteredTests.length} of {suiteDetail.test_cases?.length || 0} tests
                  </span>
                </div>

                {showFilters && (
                  <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex flex-wrap items-end gap-4">
                    {/* Protocol filter */}
                    <div>
                      <label className="text-xs font-medium text-gray-500 block mb-1">
                        Protocol
                      </label>
                      <select
                        value={filterProtocol}
                        onChange={(e) => setFilterProtocol(e.target.value)}
                        className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                      >
                        <option value="">All Protocols</option>
                        {uniqueProtocols.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Severity filter */}
                    <div>
                      <label className="text-xs font-medium text-gray-500 block mb-1">
                        Severity
                      </label>
                      <select
                        value={filterSeverity}
                        onChange={(e) => setFilterSeverity(e.target.value)}
                        className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                      >
                        <option value="">All Severities</option>
                        {uniqueSeverities.map((s) => (
                          <option key={s} value={s}>
                            {s.charAt(0).toUpperCase() + s.slice(1)}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* ML Recommended filter */}
                    <div>
                      <label className="text-xs font-medium text-gray-500 block mb-1">
                        ML Recommended
                      </label>
                      <select
                        value={filterRecommended}
                        onChange={(e) => setFilterRecommended(e.target.value)}
                        className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                      >
                        <option value="">All</option>
                        <option value="true">Recommended Only</option>
                        <option value="false">Not Recommended</option>
                      </select>
                    </div>

                    {/* Clear filters */}
                    {(filterProtocol || filterSeverity || filterRecommended) && (
                      <button
                        onClick={() => {
                          setFilterProtocol("");
                          setFilterSeverity("");
                          setFilterRecommended("");
                        }}
                        className="text-xs text-red-500 hover:text-red-700 underline pb-1"
                      >
                        Clear Filters
                      </button>
                    )}
                  </div>
                )}

                {/* ============================================================
                    Test Cases Table
                    ============================================================ */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200 text-left">
                        <SortableHeader
                          label="Test ID"
                          field="test_id"
                          currentField={sortField}
                          direction={sortDirection}
                          onSort={handleSort}
                        />
                        <SortableHeader
                          label="Test Name"
                          field="name"
                          currentField={sortField}
                          direction={sortDirection}
                          onSort={handleSort}
                        />
                        <SortableHeader
                          label="Protocol"
                          field="protocol"
                          currentField={sortField}
                          direction={sortDirection}
                          onSort={handleSort}
                        />
                        <SortableHeader
                          label="Port"
                          field="port"
                          currentField={sortField}
                          direction={sortDirection}
                          onSort={handleSort}
                        />
                        <SortableHeader
                          label="Severity"
                          field="severity"
                          currentField={sortField}
                          direction={sortDirection}
                          onSort={handleSort}
                        />
                        <SortableHeader
                          label="OWASP"
                          field="owasp_iot_category"
                          currentField={sortField}
                          direction={sortDirection}
                          onSort={handleSort}
                        />
                        <SortableHeader
                          label="Risk Score"
                          field="risk_score"
                          currentField={sortField}
                          direction={sortDirection}
                          onSort={handleSort}
                        />
                        <th className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                          Rec.
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {filteredTests.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="px-4 py-12 text-center text-gray-400">
                            <Filter className="w-6 h-6 mx-auto mb-2 opacity-40" />
                            <p>No test cases match the current filters.</p>
                          </td>
                        </tr>
                      ) : (
                        filteredTests.map((test, idx) => (
                          <tr
                            key={test.test_id || test.id || idx}
                            className="hover:bg-gray-50 transition-colors"
                          >
                            <td className="px-3 py-2.5 font-mono text-xs text-gray-500 whitespace-nowrap">
                              {test.test_id || test.id || idx + 1}
                            </td>
                            <td className="px-3 py-2.5 text-gray-800 font-medium max-w-[250px] truncate">
                              {test.name || test.test_name || "Unnamed"}
                            </td>
                            <td className="px-3 py-2.5">
                              {test.protocol ? (
                                <ProtocolBadge protocol={test.protocol} />
                              ) : (
                                <span className="text-gray-300">-</span>
                              )}
                            </td>
                            <td className="px-3 py-2.5 font-mono text-xs text-gray-600">
                              {test.port || "-"}
                            </td>
                            <td className="px-3 py-2.5">
                              <SeverityBadge severity={test.severity} />
                            </td>
                            <td className="px-3 py-2.5 text-xs text-gray-600 max-w-[140px] truncate cursor-help" title={test.owasp_iot_category || ""}>
                              {test.owasp_iot_category || "-"}
                            </td>
                            <td className="px-3 py-2.5">
                              <RiskScoreBadge score={test.risk_score} />
                            </td>
                            <td className="px-3 py-2.5 text-center">
                              {test.is_recommended ? (
                                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-700">
                                  <Zap className="w-3 h-3" /> Yes
                                </span>
                              ) : (
                                <span className="text-gray-200">-</span>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SortableHeader sub-component
// ---------------------------------------------------------------------------
function SortableHeader({ label, field, currentField, direction, onSort }) {
  const isActive = currentField === field;
  return (
    <th
      className="px-3 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-700 transition"
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {isActive ? (
          direction === "desc" ? (
            <ChevronDown className="w-3 h-3 text-indigo-500" />
          ) : (
            <ChevronUp className="w-3 h-3 text-indigo-500" />
          )
        ) : (
          <ArrowUpDown className="w-3 h-3 text-gray-300" />
        )}
      </span>
    </th>
  );
}
