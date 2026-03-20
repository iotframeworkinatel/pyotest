import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Card, CardHeader, CardContent } from "./ui/card";
import { PROTOCOL_COLORS } from "../utils/chartColors";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  ComposedChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
  Cell,
} from "recharts";
import {
  FlaskConical,
  TrendingUp,
  Brain,
  BarChart3,
  ShieldCheck,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Loader2,
  Info,
  Activity,
  Target,
  Sigma,
  ChevronDown,
  ChevronUp,
  Filter,
  Crosshair,
  Gauge,
  Zap,
  Timer,
  Layers,
  FileText,
  CheckCircle2,
  Clock,
  GitCompare,
  Sparkles,
  Globe,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Colour palette
// ---------------------------------------------------------------------------

const RULE_COLORS = [
  "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#06b6d4", "#ef4444",
  "#6366f1", "#14b8a6",
];

// ---------------------------------------------------------------------------
// Safely coerce any value to a number (handles strings, null, undefined)
// ---------------------------------------------------------------------------
const N = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };

// ---------------------------------------------------------------------------
// Verdict badge
// ---------------------------------------------------------------------------
function VerdictBadge({ verdict }) {
  if (!verdict) return null;
  const v = verdict.toLowerCase();
  if (v === "supported") {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-green-100 text-green-700 border border-green-200">
        <ShieldCheck className="w-4 h-4" />
        Hypothesis Supported
      </span>
    );
  }
  if (v === "trending") {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-amber-100 text-amber-700 border border-amber-200">
        <AlertTriangle className="w-4 h-4" />
        Trending Positive
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-red-100 text-red-700 border border-red-200">
      <XCircle className="w-4 h-4" />
      Not Yet Supported
    </span>
  );
}

// ---------------------------------------------------------------------------
// Convergence badge (for H3)
// ---------------------------------------------------------------------------
function ConvergenceBadge({ status }) {
  if (!status) return null;
  const s = status.toLowerCase();
  if (s === "converging") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-700">
        <TrendingUp className="w-3 h-3" /> Converging
      </span>
    );
  }
  if (s === "stable") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
        Stable
      </span>
    );
  }
  if (s === "diverging") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
        Diverging
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-500">
      Insufficient Data
    </span>
  );
}

// ---------------------------------------------------------------------------
// Calibration verdict badge (for H4)
// ---------------------------------------------------------------------------
function CalibrationBadge({ verdict }) {
  if (!verdict) return null;
  const v = verdict.toLowerCase();
  if (v === "well_calibrated") {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-green-100 text-green-700 border border-green-200">
        <ShieldCheck className="w-4 h-4" /> Well Calibrated
      </span>
    );
  }
  if (v === "moderately_calibrated") {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-amber-100 text-amber-700 border border-amber-200">
        <AlertTriangle className="w-4 h-4" /> Moderately Calibrated
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-red-100 text-red-700 border border-red-200">
      <XCircle className="w-4 h-4" /> Poorly Calibrated
    </span>
  );
}

// ---------------------------------------------------------------------------
// Efficiency verdict badge (for H5)
// ---------------------------------------------------------------------------
function EfficiencyBadge({ verdict }) {
  if (!verdict) return null;
  const v = verdict.toLowerCase();
  if (v === "efficient") {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-green-100 text-green-700 border border-green-200">
        <ShieldCheck className="w-4 h-4" /> Efficient
      </span>
    );
  }
  if (v === "comparable") {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-amber-100 text-amber-700 border border-amber-200">
        <AlertTriangle className="w-4 h-4" /> Comparable
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-red-100 text-red-700 border border-red-200">
      <XCircle className="w-4 h-4" /> Not Efficient
    </span>
  );
}

// ---------------------------------------------------------------------------
// Small stat card
// ---------------------------------------------------------------------------
function StatCard({ icon: Icon, label, value, color = "text-blue-500", sub }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center py-4">
        <Icon className={`w-7 h-7 mb-1.5 ${color}`} />
        <span className="text-2xl font-bold text-gray-900">{value ?? "--"}</span>
        <span className="text-xs text-gray-600 font-medium mt-0.5 text-center">{label}</span>
        {sub && <span className="text-[10px] text-gray-500 mt-0.5">{sub}</span>}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-white shadow-lg rounded-lg p-3 text-sm border border-gray-200">
      <p className="font-semibold text-gray-800 mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{ color: entry.color || entry.stroke || entry.fill }}>
          {entry.name}: {typeof entry.value === "number" ? entry.value.toFixed(3) : entry.value}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Collapsible section
// ---------------------------------------------------------------------------
function Section({ title, icon: Icon, children, defaultOpen = true, loading: isLoading = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="mb-6">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2 text-lg font-bold text-gray-900">
          {Icon && <Icon className="w-5 h-5 text-amber-500" />}
          {title}
          {isLoading && <Loader2 className="w-4 h-4 animate-spin text-amber-400 ml-2" />}
        </div>
        {open ? (
          <ChevronUp className="w-4 h-4 text-gray-500" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-500" />
        )}
      </button>
      {open && (
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-gray-400">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              <span className="text-sm">Loading...</span>
            </div>
          ) : (
            children
          )}
        </CardContent>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Inline hypothesis stats card
// ---------------------------------------------------------------------------
function HypothesisStatsCard({ stats, testLabel, statLabel, statValue, pValue, effectSize, effectLabel, verdict }) {
  if (!stats && !verdict) return null;
  return (
    <div className="mt-4 rounded-xl bg-gray-50 border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-3">
        <Sigma className="w-4 h-4 text-indigo-500" />
        <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
          Statistical Test
        </h5>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {testLabel && (
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Test</p>
            <p className="text-xs font-medium text-gray-800">{testLabel}</p>
          </div>
        )}
        {statValue != null && (
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">{statLabel || "Statistic"}</p>
            <p className="text-sm font-bold text-gray-900">{typeof statValue === "number" ? statValue.toFixed(4) : statValue}</p>
          </div>
        )}
        {pValue != null && (
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">p-value</p>
            <p className="text-sm font-bold text-gray-900">
              {N(pValue).toExponential(2)}
              {N(pValue) < 0.05 ? (
                <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">sig</span>
              ) : (
                <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">n.s.</span>
              )}
            </p>
          </div>
        )}
        {effectSize != null && (
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">{effectLabel || "Effect Size"}</p>
            <p className="text-sm font-bold text-gray-900">
              {typeof effectSize === "number" ? effectSize.toFixed(4) : effectSize}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Hypothesis({ apiUrl, visible = true }) {
  const [iterations, setIterations] = useState([]);
  const [availableProtocols, setAvailableProtocols] = useState([]);
  const [selectedProtocol, setSelectedProtocol] = useState(null);

  const [stats, setStats] = useState(null);
  const [recEffectiveness, setRecEffectiveness] = useState(null);
  const [protocolConvergence, setProtocolConvergence] = useState(null);
  const [riskCalibration, setRiskCalibration] = useState(null);
  const [execEfficiency, setExecEfficiency] = useState(null);
  const [discoveryCoverage, setDiscoveryCoverage] = useState(null);
  const [crossFramework, setCrossFramework] = useState(null);
  const [temporalValidation, setTemporalValidation] = useState(null);
  const [baselineComparison, setBaselineComparison] = useState(null);
  const [generalization, setGeneralization] = useState(null);
  const [synthesis, setSynthesis] = useState(null);
  const [frameworkInteraction, setFrameworkInteraction] = useState(null);
  const [llmEffectiveness, setLlmEffectiveness] = useState(null);
  const [ablation, setAblation] = useState(null);
  const [dynamicComparison, setDynamicComparison] = useState(null);
  const [iterDebug, setIterDebug] = useState(null);
  const [sectionLoading, setSectionLoading] = useState({
    iterationMetrics: true,

    statisticalTests: true,
    recEffectiveness: true,
    protocolConvergence: true,
    riskCalibration: true,
    execEfficiency: true,
    discoveryCoverage: true,
    crossFramework: true,
    temporalValidation: true,
    baselineComparison: true,
    generalization: true,
    synthesis: true,
    frameworkInteraction: true,
    llmEffectiveness: true,
    ablation: true,
    dynamicComparison: true,
  });
  const [refreshing, setRefreshing] = useState(false);
  const [fetchErrors, setFetchErrors] = useState([]);
  const [simFilter, setSimFilter] = useState("deterministic");
  const [availableSimModes, setAvailableSimModes] = useState([]);
  const [modeMetadata, setModeMetadata] = useState({});
  const [automlFilter, setAutomlFilter] = useState("h2o");
  const [availableFrameworks, setAvailableFrameworks] = useState(["h2o"]);

  // -----------------------------------------------------------------------
  // Fetchers
  // -----------------------------------------------------------------------
  const fetchStats = useCallback(async (protocol = null, simMode = "all", amlTool = null) => {
    setSectionLoading((prev) => ({ ...prev, statisticalTests: true }));
    try {
      const params = new URLSearchParams();
      if (protocol) params.set("protocol", protocol);
      if (simMode && simMode !== "all") params.set("simulation_mode", simMode);
      if (amlTool && amlTool !== "all") params.set("automl_tool", amlTool);
      const qs = params.toString() ? `?${params.toString()}` : "";
      const res = await fetch(`${apiUrl}/api/hypothesis/statistical-tests${qs}`);
      if (res.ok) {
        const d = await res.json();
        setStats(d);
      }
    } catch (err) {
      console.error("[Hypothesis] stats fetch error:", err);
    } finally {
      setSectionLoading((prev) => ({ ...prev, statisticalTests: false }));
    }
  }, [apiUrl]);

  // Helper: fetch a single section and update its loading state independently
  const fetchSection = useCallback(async (name, url, onSuccess) => {
    setSectionLoading((prev) => ({ ...prev, [name]: true }));
    try {
      const res = await fetch(url);
      if (res.ok) {
        const d = await res.json();
        onSuccess(d);
      } else {
        setFetchErrors((prev) => [...prev, `${name}: HTTP ${res.status}`]);
      }
    } catch (err) {
      setFetchErrors((prev) => [...prev, `${name}: ${err.message}`]);
    } finally {
      setSectionLoading((prev) => ({ ...prev, [name]: false }));
    }
  }, []);

  const synthesisFetchedRef = useRef(false);

  const fetchAll = useCallback((protocol = null, simMode = "all") => {
    const sq = simMode && simMode !== "all" ? `&simulation_mode=${encodeURIComponent(simMode)}` : "";
    const aq = automlFilter && automlFilter !== "all" ? `&automl_tool=${encodeURIComponent(automlFilter)}` : "";
    const t = `_t=${Date.now()}`;

    setFetchErrors([]);
    synthesisFetchedRef.current = false; // allow deferred synthesis to re-trigger

    // Fire ALL fetches independently -- each updates its own state on completion
    fetchSection("iterationMetrics",
      `${apiUrl}/api/hypothesis/iteration-metrics?${t}${sq}${aq}`,
      (d) => {
        setIterations(d.iterations || []);
        setIterDebug(d._debug || null);
        if (d.available_protocols) setAvailableProtocols(d.available_protocols);
      }
    );

    fetchStats(protocol, simMode, automlFilter);
    fetchSection("recEffectiveness",
      `${apiUrl}/api/hypothesis/recommendation-effectiveness?${t}${sq}${aq}`,
      setRecEffectiveness
    );
    fetchSection("protocolConvergence",
      `${apiUrl}/api/hypothesis/protocol-convergence?${t}${sq}${aq}`,
      setProtocolConvergence
    );
    fetchSection("riskCalibration",
      `${apiUrl}/api/hypothesis/risk-calibration?${t}${sq}${aq}`,
      setRiskCalibration
    );
    fetchSection("execEfficiency",
      `${apiUrl}/api/hypothesis/execution-efficiency?${t}${sq}${aq}`,
      setExecEfficiency
    );
    fetchSection("discoveryCoverage",
      `${apiUrl}/api/hypothesis/discovery-coverage?${t}${aq}`,
      setDiscoveryCoverage
    );
    fetchSection("crossFramework",
      `${apiUrl}/api/hypothesis/cross-framework?${t}${sq}`,
      setCrossFramework
    );
    fetchSection("temporalValidation",
      `${apiUrl}/api/hypothesis/temporal-validation?${t}${sq}${aq}`,
      setTemporalValidation
    );
    fetchSection("baselineComparison",
      `${apiUrl}/api/hypothesis/baseline-comparison?${t}${sq}`,
      setBaselineComparison
    );
    fetchSection("generalization",
      `${apiUrl}/api/hypothesis/generalization?${t}${sq}${aq}`,
      setGeneralization
    );
    fetchSection("frameworkInteraction",
      `${apiUrl}/api/hypothesis/framework-interaction?${t}`,
      setFrameworkInteraction
    );
    fetchSection("llmEffectiveness",
      `${apiUrl}/api/hypothesis/llm-effectiveness?${t}${sq}${aq}`,
      setLlmEffectiveness
    );
    fetchSection("ablation",
      `${apiUrl}/api/hypothesis/ablation?${t}${sq}`,
      setAblation
    );
    fetchSection("dynamicComparison",
      `${apiUrl}/api/hypothesis/dynamic-features-comparison?${t}${sq}${aq}`,
      setDynamicComparison
    );
    // synthesis is deferred — see useEffect below that triggers it after other sections finish
  }, [apiUrl, fetchSection, fetchStats, automlFilter]);

  // Refetch when AutoML filter changes
  useEffect(() => {
    if (hasMountedRef.current) {
      fetchAll(selectedProtocol, simFilter);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [automlFilter]);

  // Defer synthesis fetch — runs after all other hypothesis sections finish loading.
  // This avoids double-computation on cold cache since synthesis internally calls all
  // hypothesis functions, and by then individual endpoint caches are warm.
  useEffect(() => {
    const otherSections = [
      "iterationMetrics", "statisticalTests",
      "recEffectiveness", "protocolConvergence", "riskCalibration",
      "execEfficiency", "discoveryCoverage", "crossFramework",
      "temporalValidation", "baselineComparison", "generalization",
      "frameworkInteraction", "llmEffectiveness", "ablation", "dynamicComparison",
    ];
    const allOthersDone = otherSections.every((s) => !sectionLoading[s]);
    if (allOthersDone && hasMountedRef.current && !synthesisFetchedRef.current) {
      synthesisFetchedRef.current = true;
      const sq = simFilter && simFilter !== "all" ? `&simulation_mode=${encodeURIComponent(simFilter)}` : "";
      const aq = automlFilter && automlFilter !== "all" ? `&automl_tool=${encodeURIComponent(automlFilter)}` : "";
      fetchSection("synthesis",
        `${apiUrl}/api/hypothesis/synthesis?_t=${Date.now()}${sq}${aq}`,
        setSynthesis
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionLoading]);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    // Invalidate backend caches first so we get fresh data
    try {
      await fetch(`${apiUrl}/api/hypothesis/invalidate-cache`, { method: "POST" });
    } catch (_) {}
    // Refresh mode metadata alongside hypothesis data
    try {
      const modeRes = await fetch(`${apiUrl}/api/hypothesis/available-simulation-modes`);
      if (modeRes.ok) {
        const d = await modeRes.json();
        setAvailableSimModes(d.modes || []);
        setModeMetadata(d.mode_metadata || {});
      }
    } catch (_) {}
    fetchAll(selectedProtocol, simFilter);
    setRefreshing(false);
  }, [apiUrl, fetchAll, selectedProtocol, simFilter]);

  const hasMountedRef = useRef(false);

  useEffect(() => {
    // Fetch available simulation modes on mount
    fetch(`${apiUrl}/api/hypothesis/available-simulation-modes`)
      .then((r) => r.json())
      .then((d) => {
        setAvailableSimModes(d.modes || []);
        setModeMetadata(d.mode_metadata || {});
      })
      .catch(() => {});
    // Fetch available AutoML frameworks
    fetch(`${apiUrl}/api/automl/frameworks`)
      .then((r) => r.json())
      .then((d) => {
        const fws = (d.frameworks || []).map((f) => f.name);
        if (fws.length > 0) setAvailableFrameworks(fws);
      })
      .catch(() => {});
    fetchAll(null, simFilter);
    hasMountedRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-refresh when the tab becomes visible (after initial mount)
  useEffect(() => {
    if (visible && hasMountedRef.current) {
      fetchAll(selectedProtocol, simFilter);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // Refetch all data when simulation filter changes
  useEffect(() => {
    if (hasMountedRef.current) {
      fetchAll(selectedProtocol, simFilter);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simFilter]);

  // Refetch stats only when selected protocol changes (simFilter/automlFilter
  // changes already trigger fetchAll which calls fetchStats internally)
  useEffect(() => {
    if (hasMountedRef.current && selectedProtocol) {
      fetchStats(selectedProtocol, simFilter, automlFilter);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProtocol]);

  // -----------------------------------------------------------------------
  // Derived data
  // -----------------------------------------------------------------------
  const ROLLING_WINDOW = 10;

  const iterData = useMemo(() => {
    if (!Array.isArray(iterations)) return [];
    const rows = iterations.map((it, idx) => {
      const row = {
        iteration: idx + 1,
        label: it.experiment || `Iter ${idx + 1}`,
        detection_rate: it.detection_rate != null ? +(it.detection_rate * 100).toFixed(2) : 0,
        total_tests: it.total_tests || 0,
        total_vulns: it.total_vulns || 0,
        unique_protocols: it.unique_protocols || 0,
        avg_exec_ms: it.avg_execution_time_ms || 0,
        new_vulns: it.new_vulns ?? 0,
        cumulative_unique_vulns: it.cumulative_unique_vulns ?? 0,
      };
      if (it.by_protocol) {
        for (const [proto, metrics] of Object.entries(it.by_protocol)) {
          row[`rate_${proto}`] =
            metrics.detection_rate != null
              ? +(metrics.detection_rate * 100).toFixed(2)
              : null;
        }
      }
      return row;
    });
    // Add rolling mean (window = ROLLING_WINDOW) for the global detection rate
    rows.forEach((row, idx) => {
      const start = Math.max(0, idx - ROLLING_WINDOW + 1);
      const window = rows.slice(start, idx + 1);
      row.rolling_mean = +(window.reduce((s, r) => s + r.detection_rate, 0) / window.length).toFixed(2);
    });
    return rows;
  }, [iterations]);

  // Mean ± σ across all iterations
  const { meanRate, stdRate } = useMemo(() => {
    if (iterData.length === 0) return { meanRate: null, stdRate: null };
    const rates = iterData.map(r => r.detection_rate);
    const mean = rates.reduce((s, v) => s + v, 0) / rates.length;
    const std = Math.sqrt(rates.reduce((s, v) => s + (v - mean) ** 2, 0) / rates.length);
    return { meanRate: mean, stdRate: std };
  }, [iterData]);

  const totalIter = iterData.length;

  // Trend label derived from spearman_rho + significance
  const trendLabel = useMemo(() => {
    if (!stats || stats.spearman_rho == null) return null;
    const rho = N(stats.spearman_rho);
    const sig = stats.spearman_p != null && N(stats.spearman_p) < 0.05;
    if (!sig || Math.abs(rho) < 0.1) return { icon: "→", label: "Stable", color: "text-green-600" };
    if (rho > 0) return { icon: "↑", label: "Improving", color: "text-blue-600" };
    return { icon: "↓", label: "Degrading", color: "text-red-500" };
  }, [stats]);


  // H2: Recommendation effectiveness bar data
  const isStrategyFallback = recEffectiveness?.mode === "strategy_fallback";
  const recBarData = useMemo(() => {
    if (!recEffectiveness?.overall) return [];
    const o = recEffectiveness.overall;
    const recLabel = isStrategyFallback ? "ML-Generated" : "Recommended";
    const nonRecLabel = isStrategyFallback ? "Static" : "Non-Recommended";
    return [
      { group: recLabel, rate: +(N(o.recommended_rate) * 100).toFixed(1), count: N(o.recommended_count), fill: "#22c55e" },
      { group: nonRecLabel, rate: +(N(o.non_recommended_rate) * 100).toFixed(1), count: N(o.non_recommended_count), fill: "#9ca3af" },
    ];
  }, [recEffectiveness, isStrategyFallback]);

  const thresholdData = useMemo(() => {
    if (!recEffectiveness?.threshold_sweep) return [];
    return recEffectiveness.threshold_sweep.map((t) => ({
      threshold: N(t.threshold),
      precision: +(N(t.precision) * 100).toFixed(1),
      recall: +(N(t.recall) * 100).toFixed(1),
      f1: +(N(t.f1) * 100).toFixed(1),
    }));
  }, [recEffectiveness]);

  // H3: Protocol convergence bar data
  const convergenceBarData = useMemo(() => {
    if (!protocolConvergence?.protocols) return [];
    return protocolConvergence.protocols
      .filter((p) => p.status !== "insufficient_data" && p.slope != null)
      .map((p) => ({
        protocol: p.protocol,
        slope: +(N(p.slope) * 100).toFixed(3),
        status: p.status,
      }));
  }, [protocolConvergence]);

  // H4: Calibration curve data
  const calibrationData = useMemo(() => {
    if (!riskCalibration?.calibration_curve) return [];
    return riskCalibration.calibration_curve.map((bin) => ({
      midpoint: +((N(bin.bin_start) + N(bin.bin_end)) / 2).toFixed(2),
      predicted: +(N(bin.predicted_mean) * 100).toFixed(1),
      observed: +(N(bin.observed_rate) * 100).toFixed(1),
      count: N(bin.count),
      label: `${(N(bin.bin_start) * 100).toFixed(0)}-${(N(bin.bin_end) * 100).toFixed(0)}%`,
    }));
  }, [riskCalibration]);

  // -----------------------------------------------------------------------
  // Derived loading helpers
  // -----------------------------------------------------------------------
  const anyLoading = Object.entries(sectionLoading)
    .filter(([key]) => key !== "synthesis") // synthesis loads last & is slow; don't block UI
    .some(([, v]) => v);

  // -----------------------------------------------------------------------
  // Render — sections appear progressively as their data arrives
  // -----------------------------------------------------------------------
  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
          <FlaskConical className="w-6 h-6 text-amber-500" />
          Hypothesis Validation
        </h2>
        <div className="flex items-center gap-3">
          {/* Simulation mode selector — each mode is isolated */}
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <label className="text-sm text-gray-500 font-medium">Experiment:</label>
            <select
              value={simFilter}
              onChange={(e) => setSimFilter(e.target.value)}
              className="border border-gray-300 rounded-lg px-2.5 py-2 text-sm focus:ring-2 focus:ring-amber-400 focus:outline-none bg-white"
            >
              {availableSimModes.map((m) => {
                const meta = modeMetadata[m];
                const seedStr = meta?.seeds?.length ? ` (seed ${meta.seeds.join(", ")})` : "";
                return (
                  <option key={m} value={m}>
                    {m.charAt(0).toUpperCase() + m.slice(1)}{seedStr}
                  </option>
                );
              })}
            </select>
            {/* Mode metadata badge */}
            {modeMetadata[simFilter] && (
              <span className="text-xs text-gray-400 bg-gray-100 rounded px-2 py-0.5">
                {modeMetadata[simFilter].rows} rows
                {modeMetadata[simFilter].seeds?.length > 0 &&
                  ` · seed ${modeMetadata[simFilter].seeds.join(", ")}`}
                {modeMetadata[simFilter].iterations?.length > 0 &&
                  ` · ${modeMetadata[simFilter].iterations.length} iters`}
              </span>
            )}
          </div>
          {/* AutoML Framework selector */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-500 font-medium">AutoML:</label>
            <select
              value={automlFilter}
              onChange={(e) => setAutomlFilter(e.target.value)}
              className="border border-gray-300 rounded-lg px-2.5 py-2 text-sm focus:ring-2 focus:ring-amber-400 focus:outline-none bg-white"
            >
              {availableFrameworks.map((fw) => (
                <option key={fw} value={fw}>
                  {fw === "h2o" ? "H2O AutoML" :
                   fw === "autogluon" ? "AutoGluon" :
                   fw === "pycaret" ? "PyCaret" :
                   fw === "tpot" ? "TPOT" :
                   fw === "autosklearn" ? "auto-sklearn" : fw}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={refreshAll}
            disabled={refreshing || anyLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 text-white text-sm font-medium hover:bg-amber-600 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing || anyLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Fetch error banner */}
      {fetchErrors.length > 0 && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
          <p className="font-semibold mb-1">Some hypothesis data failed to load:</p>
          <ul className="list-disc list-inside text-xs text-red-600 space-y-0.5">
            {fetchErrors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
          <p className="text-xs text-red-500 mt-1">Click Refresh to retry.</p>
        </div>
      )}

      {/* ================================================================= */}
      {/* H1 — Detection Rate Stability (single unified section)           */}
      {/* ================================================================= */}
      <Section
        title="H1 — Detection Rate Stability"
        icon={Activity}
        loading={sectionLoading.iterationMetrics || sectionLoading.statisticalTests}
      >
        {/* Hypothesis statement */}
        <Card className="mb-4 border-l-4 border-l-amber-400">
          <CardContent className="py-3">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-amber-600 uppercase tracking-wider mb-1">
                  H1 — Detection Rate Stability
                </p>
                <p className="text-gray-700 text-sm leading-relaxed">
                  The ML-driven pipeline maintains stable vulnerability detection rates
                  over successive iterations, without significant degradation despite environmental dynamics.
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Supported = no significant decline (Spearman p &gt; 0.05) and negligible effect size (|d| &lt; 0.5).
                </p>
              </div>
              <div className="shrink-0">
                <VerdictBadge verdict={stats?.verdict} />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* KPI row */}
        <div className="grid grid-cols-3 gap-4 mb-5">
          <StatCard
            icon={Target}
            label="Mean Detection Rate"
            value={meanRate != null ? `${meanRate.toFixed(1)}%` : "--"}
            color="text-amber-500"
            sub={stdRate != null ? `σ = ${stdRate.toFixed(1)}% over ${totalIter} iterations` : `${totalIter} iterations`}
          />
          <StatCard
            icon={TrendingUp}
            label="Trend"
            value={trendLabel ? `${trendLabel.icon} ${trendLabel.label}` : "--"}
            color={trendLabel?.color ?? "text-gray-500"}
            sub={
              stats?.spearman_rho != null
                ? `ρ = ${N(stats.spearman_rho).toFixed(3)}, p = ${stats.spearman_p != null ? N(stats.spearman_p).toFixed(2) : "--"}`
                : "Spearman rank correlation"
            }
          />
          <StatCard
            icon={Sigma}
            label="Early vs Late Drift"
            value={stats?.cohens_d != null ? `d = ${N(stats.cohens_d).toFixed(3)}` : "--"}
            color={
              stats?.cohens_d_interpretation === "negligible" ? "text-green-500"
              : stats?.cohens_d_interpretation === "small" ? "text-yellow-500"
              : "text-red-500"
            }
            sub={stats?.cohens_d_interpretation ? `Effect size: ${stats.cohens_d_interpretation}` : "Cohen's d (early vs late)"}
          />
        </div>

        {/* Chart */}
        {availableProtocols.length > 0 && (
          <div className="flex items-center gap-3 mb-3">
            <Filter className="w-4 h-4 text-gray-500" />
            <span className="text-sm font-medium text-gray-700">Protocol:</span>
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => setSelectedProtocol(null)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  selectedProtocol === null ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                All Protocols
              </button>
              {availableProtocols.map((proto) => (
                <button
                  key={proto}
                  onClick={() => setSelectedProtocol(proto)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    selectedProtocol === proto ? "text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                  }`}
                  style={selectedProtocol === proto ? { backgroundColor: PROTOCOL_COLORS[proto] || "#6b7280" } : {}}
                >
                  {proto}
                </button>
              ))}
            </div>
          </div>
        )}

        {iterData.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2" />
            <p className="text-sm">No iteration data yet.</p>
            <p className="text-xs mt-1">Run test suites multiple times to see convergence trends.</p>
            {iterDebug && (
              <div className="mt-4 text-left bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-xs text-gray-500 font-mono max-w-md">
                <p className="font-semibold text-gray-600 mb-1">Debug Info:</p>
                <p>Files found: {iterDebug.files_found ?? "?"}</p>
                <p>Files parsed OK: {iterDebug.files_parsed_ok ?? "?"}</p>
                {iterDebug.parse_errors?.length > 0 && (
                  <div className="mt-1 text-red-500">
                    <p className="font-semibold">Parse errors:</p>
                    {iterDebug.parse_errors.map((e, i) => (
                      <p key={i} className="truncate" title={e}>{e}</p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={iterData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="iteration" tick={{ fontSize: 12 }} label={{ value: "Iteration", position: "insideBottomRight", offset: -5, fontSize: 12 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} label={{ value: "Detection Rate (%)", angle: -90, position: "insideLeft", fontSize: 12 }} />
              <Tooltip content={<ChartTooltip />} />
              <Legend />
              <Line type="monotone" dataKey="detection_rate" name="Global Detection Rate (%)" stroke={selectedProtocol ? "#d1d5db" : "#93c5fd"} strokeWidth={selectedProtocol ? 1 : 1.5} dot={false} activeDot={selectedProtocol ? false : { r: 5 }} />
              {!selectedProtocol && (
                <Line type="monotone" dataKey="rolling_mean" name={`${ROLLING_WINDOW}-iter Rolling Mean (%)`} stroke="#2563eb" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
              )}
              {selectedProtocol && (
                <Line type="monotone" dataKey={`rate_${selectedProtocol}`} name={`${selectedProtocol} Detection Rate (%)`} stroke={PROTOCOL_COLORS[selectedProtocol] || "#3b82f6"} strokeWidth={2.5} dot={{ r: 3, fill: PROTOCOL_COLORS[selectedProtocol] || "#3b82f6" }} activeDot={{ r: 5 }} connectNulls />
              )}
              {stats?.spearman_rho != null && (
                <ReferenceLine y={meanRate ?? 0} stroke="#9ca3af" strokeDasharray="4 4" label={{ value: "Mean", position: "left", fontSize: 11, fill: "#9ca3af" }} />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}

        {/* Stat cards */}
        {stats && !stats.error && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
            <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
              <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Trend Test — Spearman ρ</h5>
              <div className="flex items-baseline gap-2">
                <span className="text-xl font-bold text-gray-800">ρ = {stats.spearman_rho != null ? N(stats.spearman_rho).toFixed(3) : "--"}</span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${stats.spearman_significant ? "bg-orange-100 text-orange-700" : "bg-green-100 text-green-700"}`}>
                  {stats.spearman_significant ? "significant" : "not significant"}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">p = {stats.spearman_p != null ? N(stats.spearman_p).toFixed(3) : "--"} · ρ ≈ 0 means no trend</p>
            </div>
            <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
              <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Early vs Late Drift — Cohen's d</h5>
              <div className="flex items-baseline gap-2">
                <span className="text-xl font-bold text-gray-800">d = {stats.cohens_d != null ? N(stats.cohens_d).toFixed(3) : "--"}</span>
                {stats.cohens_d_interpretation && (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    stats.cohens_d_interpretation === "negligible" ? "bg-green-100 text-green-700"
                    : stats.cohens_d_interpretation === "small" ? "bg-yellow-100 text-yellow-700"
                    : "bg-red-100 text-red-700"
                  }`}>{stats.cohens_d_interpretation}</span>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {stats.early_mean != null && stats.late_mean != null
                  ? `Early ${(N(stats.early_mean) * 100).toFixed(1)}% → Late ${(N(stats.late_mean) * 100).toFixed(1)}%`
                  : "Practical drift between first and last half"}
              </p>
            </div>
            <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
              <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Drift Range — 95% CI</h5>
              <div className="flex items-baseline gap-2">
                <span className="text-xl font-bold text-gray-800">
                  {stats.ci_95?.[0] != null && stats.ci_95?.[1] != null
                    ? `[${(N(stats.ci_95[0]) * 100).toFixed(1)}%, ${(N(stats.ci_95[1]) * 100).toFixed(1)}%]`
                    : "--"}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">Late − early · straddles zero = stable</p>
            </div>
          </div>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H2 — Recommendation Effectiveness                                 */}
      {/* ================================================================= */}
      <Section title="H2 — Recommendation Effectiveness" icon={Crosshair} loading={sectionLoading.recEffectiveness}>
        {!recEffectiveness || recEffectiveness.error ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">
              {recEffectiveness?.error || "No recommendation data yet."}
            </p>
            <p className="text-xs mt-1">Train the ML model and run test suites to see recommendation effectiveness.</p>
          </div>
        ) : (
          <>
            {/* H2 hypothesis statement */}
            <Card className="mb-4 border-l-4 border-l-green-400">
              <CardContent className="py-3">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-green-600 uppercase tracking-wider mb-1">
                      H2 — Recommendation Effectiveness
                    </h3>
                    <p className="text-gray-700 text-sm leading-relaxed">
                      {isStrategyFallback
                        ? "ML-scored tests (recommended by risk model) find vulnerabilities at a higher rate than static tests (strategy-based comparison; retrain model for risk-score analysis)."
                        : "ML-recommended tests (risk score \u2265 0.5) find vulnerabilities at a significantly higher rate than non-recommended tests."}
                    </p>
                  </div>
                  <div className="shrink-0">
                    <VerdictBadge verdict={recEffectiveness.verdict} />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* KPIs */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <StatCard
                icon={Target}
                label="Recommended Rate"
                value={recEffectiveness.overall?.recommended_rate != null ? `${(N(recEffectiveness.overall.recommended_rate) * 100).toFixed(1)}%` : "--"}
                color="text-green-500"
              />
              <StatCard
                icon={XCircle}
                label="Non-Rec. Rate"
                value={recEffectiveness.overall?.non_recommended_rate != null ? `${(N(recEffectiveness.overall.non_recommended_rate) * 100).toFixed(1)}%` : "--"}
                color="text-gray-500"
              />
              <StatCard
                icon={TrendingUp}
                label="Lift"
                value={recEffectiveness.overall?.lift != null ? `${N(recEffectiveness.overall.lift).toFixed(2)}x` : "--"}
                color="text-blue-500"
                sub="Rec. rate / overall rate"
              />
              <StatCard
                icon={Sigma}
                label="Fisher p-value"
                value={recEffectiveness.overall?.fisher_p != null ? N(recEffectiveness.overall.fisher_p).toExponential(2) : "--"}
                color="text-purple-500"
                sub="< 0.05 = significant"
              />
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Recommended vs Non-Recommended bar chart */}
              <div>
                <h4 className="text-sm font-semibold text-gray-600 mb-3">Detection Rate Comparison</h4>
                {recBarData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={recBarData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="group" tick={{ fontSize: 12 }} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} label={{ value: "%", position: "top", offset: 0, fontSize: 11 }} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="rate" name="Detection Rate (%)" radius={[4, 4, 0, 0]}>
                        {recBarData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-[260px] text-gray-500 text-sm">No data</div>
                )}
              </div>

              {/* Threshold sweep P/R/F1 */}
              <div>
                <h4 className="text-sm font-semibold text-gray-600 mb-3">Threshold Sweep (Precision / Recall / F1)</h4>
                {thresholdData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={thresholdData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="threshold" tick={{ fontSize: 11 }} label={{ value: "Threshold", position: "insideBottomRight", offset: -5, fontSize: 11 }} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} label={{ value: "%", position: "top", offset: 0, fontSize: 11 }} />
                      <Tooltip content={<ChartTooltip />} />
                      <Legend />
                      <Line type="monotone" dataKey="precision" name="Precision" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="recall" name="Recall" stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="f1" name="F1 Score" stroke="#f59e0b" strokeWidth={2.5} dot={{ r: 4 }} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-[260px] text-gray-500 text-sm">No data</div>
                )}
              </div>
            </div>
          </>
        )}
      </Section>


      {/* ================================================================= */}
      {/* H3 — Protocol Convergence Rates                                   */}
      {/* ================================================================= */}
      <Section title="H3 — Protocol Convergence Rates" icon={TrendingUp} loading={sectionLoading.protocolConvergence}>
        {!protocolConvergence || protocolConvergence.error ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">
              {protocolConvergence?.error || "Not enough iteration data for convergence analysis."}
            </p>
            <p className="text-xs mt-1">Run test suites at least 2-3 times to see protocol convergence.</p>
          </div>
        ) : (
          <>
            {/* H3 hypothesis statement */}
            <Card className="mb-4 border-l-4 border-l-cyan-400">
              <CardContent className="py-3">
                <p className="text-sm font-semibold text-cyan-600 uppercase tracking-wider mb-1">
                  H3 — Protocol Convergence
                </p>
                <p className="text-gray-700 text-sm leading-relaxed">
                  Different protocols converge at different rates; some achieve detection plateau earlier.
                </p>
              </CardContent>
            </Card>

            {/* Summary KPIs */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <StatCard
                icon={TrendingUp}
                label="Fastest Converging"
                value={protocolConvergence.fastest_converging || "--"}
                color="text-green-500"
              />
              <StatCard
                icon={Activity}
                label="Most Stable"
                value={protocolConvergence.most_stable || "--"}
                color="text-amber-500"
              />
            </div>

            {/* Slope bar chart */}
            {convergenceBarData.length > 0 ? (
              <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-600 mb-3">Detection Rate Slope per Protocol (% per iteration)</h4>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={convergenceBarData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="protocol" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 11 }} label={{ value: "Slope (%/iter)", position: "top", offset: 0, fontSize: 10 }} />
                    <Tooltip content={<ChartTooltip />} />
                    <Bar dataKey="slope" name="Slope (% per iteration)" radius={[4, 4, 0, 0]}>
                      {convergenceBarData.map((entry, i) => (
                        <Cell key={i} fill={PROTOCOL_COLORS[entry.protocol] || "#6b7280"} />
                      ))}
                    </Bar>
                    <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 4" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="flex items-center justify-center py-8 text-gray-500 text-sm">
                No convergence data available
              </div>
            )}

            {/* Protocol detail badges */}
            {protocolConvergence.protocols && protocolConvergence.protocols.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {protocolConvergence.protocols.map((p) => (
                  <div key={p.protocol} className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm font-semibold text-gray-800">{p.protocol}</span>
                      <ConvergenceBadge status={p.status} />
                    </div>
                    <div className="text-xs text-gray-600 space-y-0.5">
                      <p>Iterations: {p.n_iterations} &middot; Rate: {p.first_rate != null ? `${(N(p.first_rate) * 100).toFixed(0)}%` : "?"} &rarr; {p.last_rate != null ? `${(N(p.last_rate) * 100).toFixed(0)}%` : "?"}</p>
                      {p.spearman_rho != null && (
                        <p>Spearman &rho; = {N(p.spearman_rho).toFixed(3)} (p = {p.spearman_p != null ? N(p.spearman_p).toExponential(1) : "?"})</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Inline overall convergence stats */}
            {protocolConvergence.overall_verdict && (
              <div className="mt-4 rounded-xl bg-gray-50 border border-gray-200 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Sigma className="w-4 h-4 text-indigo-500" />
                  <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    Overall Convergence Test
                  </h5>
                  <VerdictBadge verdict={protocolConvergence.overall_verdict} />
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Test</p>
                    <p className="text-xs font-medium text-gray-800">Mann-Whitney U (variance)</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Variance Reduction</p>
                    <p className="text-sm font-bold text-gray-900">
                      {protocolConvergence.variance_reduction_pct != null
                        ? `${N(protocolConvergence.variance_reduction_pct).toFixed(1)}%`
                        : "--"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">p-value</p>
                    <p className="text-sm font-bold text-gray-900">
                      {protocolConvergence.mann_whitney_p != null
                        ? N(protocolConvergence.mann_whitney_p).toExponential(2)
                        : "--"}
                      {protocolConvergence.mann_whitney_p != null && N(protocolConvergence.mann_whitney_p) < 0.05 ? (
                        <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">sig</span>
                      ) : protocolConvergence.mann_whitney_p != null ? (
                        <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">n.s.</span>
                      ) : null}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Protocols</p>
                    <p className="text-xs text-gray-700">
                      {protocolConvergence.converging_count || 0} converging, {protocolConvergence.stable_count || 0} stable, {protocolConvergence.diverging_count || 0} diverging
                    </p>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H4 — Risk Score Calibration                                       */}
      {/* ================================================================= */}
      <Section title="H4 — Risk Score Calibration" icon={Gauge} loading={sectionLoading.riskCalibration}>
        {!riskCalibration || riskCalibration.error ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">
              {riskCalibration?.error || "No calibration data yet."}
            </p>
            <p className="text-xs mt-1">Run test suites to generate calibration data.</p>
          </div>
        ) : (
          <>
            {/* H4 hypothesis statement */}
            <Card className="mb-4 border-l-4 border-l-purple-400">
              <CardContent className="py-3">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-purple-600 uppercase tracking-wider mb-1">
                      H4 — Risk Score Calibration
                    </p>
                    <p className="text-gray-700 text-sm leading-relaxed">
                      Predicted risk scores are well-calibrated &mdash; a test scored 0.8 finds
                      vulnerabilities approximately 80% of the time.
                    </p>
                    {riskCalibration.score_method === "heuristic" && (
                      <p className="text-xs text-amber-600 mt-1">
                        ⚡ Using empirical base-rate scoring (leave-iteration-out cross-validation). Train an ML model for model-based calibration.
                      </p>
                    )}
                  </div>
                  <div className="shrink-0">
                    <CalibrationBadge verdict={riskCalibration.verdict} />
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Calibration curve */}
              <div>
                <h4 className="text-sm font-semibold text-gray-600 mb-3">Calibration Curve</h4>
                {calibrationData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <ComposedChart data={calibrationData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis
                        dataKey="midpoint"
                        tick={{ fontSize: 11 }}
                        label={{ value: "Predicted Risk Score", position: "insideBottomRight", offset: -5, fontSize: 11 }}
                      />
                      <YAxis
                        yAxisId="left"
                        domain={[0, 100]}
                        tick={{ fontSize: 11 }}
                        label={{ value: "Rate (%)", angle: -90, position: "insideLeft", fontSize: 11 }}
                      />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
                      <Tooltip content={<ChartTooltip />} />
                      <Legend />
                      <Bar yAxisId="right" dataKey="count" name="Sample Count" fill="#e5e7eb" opacity={0.5} />
                      <Line yAxisId="left" type="monotone" dataKey="predicted" name="Predicted (%)" stroke="#3b82f6" strokeWidth={2} strokeDasharray="6 3" dot={{ r: 3 }} />
                      <Line yAxisId="left" type="monotone" dataKey="observed" name="Observed (%)" stroke="#22c55e" strokeWidth={2.5} dot={{ r: 4, fill: "#22c55e" }} />
                      <ReferenceLine yAxisId="left" segment={[{ x: 0, y: 0 }, { x: 1, y: 100 }]} stroke="#d1d5db" strokeDasharray="4 4" label={{ value: "Perfect", fontSize: 10, fill: "#9ca3af" }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-[300px] text-gray-500 text-sm">No calibration data</div>
                )}
              </div>

              {/* Calibration metrics */}
              <div>
                <h4 className="text-sm font-semibold text-gray-600 mb-3">Calibration Metrics</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                    <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Brier Score</h5>
                    <span className="text-xl font-bold text-gray-800">
                      {riskCalibration.brier_score != null ? N(riskCalibration.brier_score).toFixed(4) : "--"}
                    </span>
                    <p className="text-xs text-gray-500 mt-1">Lower is better (0 = perfect)</p>
                  </div>
                  <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                    <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">ECE</h5>
                    <span className="text-xl font-bold text-gray-800">
                      {riskCalibration.ece != null ? N(riskCalibration.ece).toFixed(4) : "--"}
                    </span>
                    <p className="text-xs text-gray-500 mt-1">Expected Calibration Error</p>
                  </div>
                  <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                    <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">MCE</h5>
                    <span className="text-xl font-bold text-gray-800">
                      {riskCalibration.mce != null ? N(riskCalibration.mce).toFixed(4) : "--"}
                    </span>
                    <p className="text-xs text-gray-500 mt-1">Max Calibration Error</p>
                  </div>
                  <div className="rounded-xl bg-gray-50 p-4 border border-gray-200 flex flex-col items-center justify-center">
                    <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">Verdict</h5>
                    <CalibrationBadge verdict={riskCalibration.verdict} />
                    {riskCalibration.total_predictions != null && (
                      <p className="text-xs text-gray-500 mt-2">{riskCalibration.total_predictions} predictions</p>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Score-method comparison (model vs heuristic) */}
            {riskCalibration.score_method_comparison && Object.keys(riskCalibration.score_method_comparison).length > 0 && (
              <div className="mt-6">
                <h4 className="text-sm font-semibold text-gray-600 mb-3">Score Method Comparison</h4>
                {riskCalibration.tautology_warning && (
                  <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                      <div>
                        <p className="text-sm font-semibold text-amber-700">Tautology Warning</p>
                        <p className="text-xs text-amber-600 mt-1">{riskCalibration.tautology_explanation}</p>
                      </div>
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Object.entries(riskCalibration.score_method_comparison).map(([method, data]) => (
                    <div key={method} className={`rounded-xl p-4 border ${method === "model" ? "bg-blue-50 border-blue-200" : "bg-gray-50 border-gray-200"}`}>
                      <h5 className="text-xs font-semibold uppercase tracking-wide mb-2"
                          style={{ color: method === "model" ? "#2563eb" : "#6b7280" }}>
                        {method} {method === "heuristic" && "(base-rate lookup)"}
                      </h5>
                      <div className="space-y-1 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-500">ECE</span>
                          <span className="font-mono font-semibold">{N(data.ece).toFixed(4)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Brier</span>
                          <span className="font-mono font-semibold">{N(data.brier).toFixed(4)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">MCE</span>
                          <span className="font-mono font-semibold">{N(data.mce).toFixed(4)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">n</span>
                          <span className="font-mono">{data.n}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H5 — Execution Efficiency                                        */}
      {/* ================================================================= */}
      <Section title="H5 — Execution Efficiency" icon={Zap} loading={sectionLoading.execEfficiency}>
        {!execEfficiency || !execEfficiency.summary?.has_recommendations ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">
              No execution efficiency data yet.
            </p>
            <p className="text-xs mt-1">Train the ML model and run scored test suites to see efficiency analysis.</p>
          </div>
        ) : (
          <>
            {/* H5 hypothesis statement */}
            <Card className="mb-4 border-l-4 border-l-emerald-400">
              <CardContent className="py-3">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-emerald-600 uppercase tracking-wider mb-1">
                      H5 — Execution Efficiency
                    </p>
                    <p className="text-gray-700 text-sm leading-relaxed">
                      ML-driven test selection achieves comparable vulnerability detection coverage
                      while significantly reducing execution overhead (fewer tests, less time).
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                      Compares recommended subset vs full suite using efficiency ratio (detection coverage &divide; test fraction).
                      Ratio &gt; 1.0 means ML adds value.
                    </p>
                  </div>
                  <div className="shrink-0">
                    <EfficiencyBadge verdict={execEfficiency.verdict} />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* KPI cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <StatCard
                icon={Filter}
                label="Test Reduction"
                value={execEfficiency.summary.avg_test_reduction_pct != null
                  ? `${N(execEfficiency.summary.avg_test_reduction_pct).toFixed(1)}%`
                  : "--"}
                color="text-blue-500"
                sub="Fewer tests to run"
              />
              <StatCard
                icon={Target}
                label="Detection Coverage"
                value={execEfficiency.summary.avg_detection_coverage_pct != null
                  ? `${N(execEfficiency.summary.avg_detection_coverage_pct).toFixed(1)}%`
                  : "--"}
                color="text-green-500"
                sub="Vulns still found"
              />
              <StatCard
                icon={Zap}
                label="Efficiency Ratio"
                value={execEfficiency.summary.avg_efficiency_ratio != null
                  ? `${N(execEfficiency.summary.avg_efficiency_ratio).toFixed(2)}×`
                  : "--"}
                color="text-amber-500"
                sub="> 1.0 = ML adds value"
              />
              <StatCard
                icon={Timer}
                label="Time Saved"
                value={execEfficiency.summary.avg_time_saved_pct != null
                  ? `${N(execEfficiency.summary.avg_time_saved_pct).toFixed(1)}%`
                  : "--"}
                color="text-purple-500"
                sub="Theoretical savings"
              />
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Stacked bar: recommended vs non-recommended */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-3">
                  Test Composition per Execution
                </h4>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={(execEfficiency.iterations || []).map((it, i) => ({
                    iteration: i + 1,
                    recommended: it.recommended_tests ?? 0,
                    nonRecommended: it.non_recommended_tests ?? 0,
                    recVulns: it.recommended_vulns ?? 0,
                    nonRecVulns: it.non_recommended_vulns ?? 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="iteration" tick={{ fontSize: 12 }} label={{ value: "Iteration", position: "bottom", offset: -2, fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend />
                    <Bar dataKey="recommended" name="Recommended Tests" stackId="tests" fill="#10b981" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="nonRecommended" name="Non-Recommended Tests" stackId="tests" fill="#d1d5db" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Line chart: efficiency ratio trend */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-3">
                  Efficiency Ratio Over Iterations
                </h4>
                <ResponsiveContainer width="100%" height={280}>
                  <ComposedChart data={(execEfficiency.iterations || []).map((it, i) => ({
                    iteration: i + 1,
                    efficiency: it.efficiency_ratio ?? 0,
                    coverage: it.detection_coverage_pct ?? 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="iteration" tick={{ fontSize: 12 }} />
                    <YAxis yAxisId="left" tick={{ fontSize: 11 }} label={{ value: "Ratio", angle: -90, position: "insideLeft", offset: 10, fontSize: 11 }} />
                    <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 11 }} label={{ value: "%", position: "top", offset: 0, fontSize: 11 }} />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend />
                    <ReferenceLine yAxisId="left" y={1} stroke="#9ca3af" strokeDasharray="4 4" label={{ value: "Baseline (1.0)", position: "right", fontSize: 10, fill: "#9ca3af" }} />
                    <Line yAxisId="left" type="monotone" dataKey="efficiency" name="Efficiency Ratio" stroke="#f59e0b" strokeWidth={2.5} dot={{ fill: "#f59e0b", r: 4 }} />
                    <Line yAxisId="right" type="monotone" dataKey="coverage" name="Detection Coverage (%)" stroke="#22c55e" strokeWidth={2} strokeDasharray="6 3" dot={{ fill: "#22c55e", r: 3 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Summary details */}
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                  Aggregate Savings
                </h5>
                <div className="space-y-1.5 text-sm text-gray-700">
                  <p>
                    <span className="font-semibold">{execEfficiency.summary.total_executions}</span> scored executions analyzed
                  </p>
                  <p>
                    Total estimated time saved:{" "}
                    <span className="font-semibold text-emerald-600">
                      {execEfficiency.summary.total_time_saved_ms != null
                        ? N(execEfficiency.summary.total_time_saved_ms) >= 60000
                          ? `${(N(execEfficiency.summary.total_time_saved_ms) / 60000).toFixed(1)} min`
                          : `${(N(execEfficiency.summary.total_time_saved_ms) / 1000).toFixed(1)}s`
                        : "--"}
                    </span>
                  </p>
                </div>
              </div>
              <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                  Interpretation
                </h5>
                <p className="text-sm text-gray-700 leading-relaxed">
                  {execEfficiency.verdict === "efficient"
                    ? "ML recommendations are highly efficient — the recommended subset detects the vast majority of vulnerabilities while requiring significantly fewer tests."
                    : execEfficiency.verdict === "comparable"
                    ? "ML recommendations show promise — the recommended subset captures a reasonable share of vulnerabilities with fewer tests. More iterations may improve separation."
                    : "ML recommendations are not yet demonstrating efficiency gains. The model may need more training data to identify high-value tests."}
                </p>
              </div>
            </div>

            {/* Inline H5 stats */}
            {execEfficiency.stats && (
              <HypothesisStatsCard
                stats={execEfficiency.stats}
                testLabel="Wilcoxon signed-rank"
                statLabel="W statistic"
                statValue={execEfficiency.stats.wilcoxon_w}
                pValue={execEfficiency.stats.wilcoxon_p}
                effectSize={execEfficiency.stats.rank_biserial_r}
                effectLabel={`Rank-biserial r (${execEfficiency.stats.rank_biserial_interpretation || ""})`}
              />
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H6 — Discovery Coverage                                          */}
      {/* ================================================================= */}
      <Section title="H6 — Discovery Coverage" icon={Target} loading={sectionLoading.discoveryCoverage}>
        {iterData.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">No iteration data yet.</p>
            <p className="text-xs mt-1">Run test suites to track new vulnerability discovery.</p>
          </div>
        ) : (
          <>
            {/* H6 hypothesis statement */}
            <Card className="mb-4 border-l-4 border-l-cyan-400">
              <CardContent className="py-3">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-cyan-600 uppercase tracking-wider mb-1">
                      H6 — Discovery Coverage
                    </p>
                    <p className="text-gray-700 text-sm leading-relaxed">
                      Dynamic simulation modes (medium, realistic) expose significantly more
                      unique vulnerability patterns than static (deterministic) environments.
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                      Compared via Kruskal-Wallis test on per-iteration new-vulnerability counts
                      with pairwise Mann-Whitney U tests. View cross-mode comparison below;
                      per-mode charts use the simulation filter above.
                    </p>
                  </div>
                  <div className="shrink-0">
                    <VerdictBadge verdict={discoveryCoverage?.verdict} />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Cross-mode statistical summary (only shown when data is available) */}
            {discoveryCoverage && discoveryCoverage.status === "ok" && (
              <div className="mb-6">
                {/* Mode comparison cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                  {Object.entries(discoveryCoverage.modes || {}).map(([mode, data]) => (
                    <div key={mode} className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                      <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                        {mode}
                      </h5>
                      <div className="space-y-1 text-sm">
                        <p className="text-gray-700">
                          <span className="font-bold text-lg text-gray-900">{data.total_unique_vulns}</span>{" "}
                          unique vulnerabilities
                        </p>
                        <p className="text-gray-500">
                          Last discovery: iter {data.last_discovery_iteration || "N/A"} / {data.total_iterations}
                        </p>
                        <p className="text-gray-500">
                          Avg new/iter: {N(data.mean_new_vulns_per_iter).toFixed(2)}
                        </p>
                        {data.lift_pct !== 0 && (
                          <p className={`font-semibold ${data.lift_pct > 0 ? "text-green-600" : "text-red-600"}`}>
                            {data.lift_pct > 0 ? "+" : ""}{N(data.lift_pct).toFixed(1)}% vs {discoveryCoverage.baseline_mode}
                          </p>
                        )}
                        {data.lift_pct === 0 && (
                          <p className="text-gray-400 text-xs font-medium">Baseline</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Kruskal-Wallis result */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                  <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                    <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                      Kruskal-Wallis Test (cross-mode)
                    </h5>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-bold text-gray-800">
                        H = {discoveryCoverage.kruskal_wallis_h != null ? N(discoveryCoverage.kruskal_wallis_h).toFixed(3) : "--"}
                      </span>
                      <span className="text-xs text-gray-500">
                        p = {discoveryCoverage.kruskal_wallis_p != null ? N(discoveryCoverage.kruskal_wallis_p).toExponential(2) : "--"}
                      </span>
                      {discoveryCoverage.kruskal_wallis_significant && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                          Significant
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      Non-parametric test for differences in new-vulnerability distributions across modes
                    </p>
                  </div>

                  {/* Pairwise comparisons */}
                  <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                    <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                      Pairwise Mann-Whitney U
                    </h5>
                    <div className="space-y-1.5">
                      {(discoveryCoverage.pairwise_tests || []).map((pw, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm">
                          <span className="text-gray-600 font-mono text-xs">
                            {pw.mode_a} vs {pw.mode_b}
                          </span>
                          <span className="text-xs text-gray-500">
                            p={pw.p_value != null ? N(pw.p_value).toExponential(2) : "--"}
                          </span>
                          {pw.significant ? (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 font-medium">
                              {pw.direction}
                            </span>
                          ) : (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                              n.s.
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Per-mode discovery charts (existing bar + cumulative line) */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <StatCard
                icon={FlaskConical}
                label="Total Iterations"
                value={iterData.length}
                color="text-blue-500"
              />
              <StatCard
                icon={Target}
                label="Unique Vulns Found"
                value={iterData.length > 0 ? iterData[iterData.length - 1].cumulative_unique_vulns : 0}
                color="text-red-500"
              />
              <StatCard
                icon={TrendingUp}
                label="New in Latest Run"
                value={iterData.length > 0 ? iterData[iterData.length - 1].new_vulns : 0}
                color="text-emerald-500"
              />
              <StatCard
                icon={Activity}
                label="Avg New / Iteration"
                value={
                  iterData.length > 0
                    ? (iterData.reduce((s, d) => s + d.new_vulns, 0) / iterData.length).toFixed(1)
                    : "--"
                }
                color="text-amber-500"
              />
            </div>

            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={iterData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="iteration"
                  tick={{ fontSize: 12 }}
                  label={{ value: "Iteration", position: "insideBottomRight", offset: -5, fontSize: 12 }}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 12 }}
                  label={{ value: "New Vulns", angle: -90, position: "insideLeft", fontSize: 12 }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 12 }}
                  label={{ value: "Cumulative", angle: 90, position: "insideRight", fontSize: 12 }}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <div className="bg-white shadow-lg rounded-lg p-3 text-sm border border-gray-200">
                        <p className="font-semibold text-gray-800 mb-1">Iteration {label}</p>
                        {payload.map((entry, i) => (
                          <p key={i} style={{ color: entry.color }}>
                            {entry.name}: {entry.value}
                          </p>
                        ))}
                      </div>
                    );
                  }}
                />
                <Legend />
                <Bar
                  yAxisId="left"
                  dataKey="new_vulns"
                  name="New Vulnerabilities"
                  fill="#10b981"
                  radius={[4, 4, 0, 0]}
                  opacity={0.8}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="cumulative_unique_vulns"
                  name="Cumulative Unique"
                  stroke="#ef4444"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: "#ef4444" }}
                  activeDot={{ r: 6 }}
                />
              </ComposedChart>
            </ResponsiveContainer>

            {/* Diminishing returns indicator */}
            {iterData.length >= 3 && (
              <div className="mt-3 px-3 py-2 rounded-lg bg-gray-50 border border-gray-200">
                <p className="text-xs text-gray-600">
                  {iterData[iterData.length - 1].new_vulns === 0
                    ? "No new vulnerabilities discovered in the latest iteration — the current test set may have saturated known attack surfaces."
                    : iterData[iterData.length - 1].new_vulns < iterData[0].new_vulns * 0.5
                    ? "Diminishing returns detected — fewer new vulnerabilities per iteration. Consider adding new test types or protocols."
                    : "Still discovering new vulnerabilities — the test set is exploring new attack vectors."}
                </p>
              </div>
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H7 — Cross-Framework Comparison                                   */}
      {/* ================================================================= */}
      <Section title="H7 — Cross-Framework Comparison" icon={Layers} defaultOpen loading={sectionLoading.crossFramework}>
        {!crossFramework || crossFramework.status === "insufficient_data" ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">
              {crossFramework?.message || "Need experiment data from at least 2 AutoML frameworks."}
            </p>
            <p className="text-xs mt-1">Run experiments with multiple frameworks (H2O, AutoGluon, PyCaret, etc.) to enable cross-framework comparison.</p>
          </div>
        ) : (
          <>
            {/* H7 hypothesis statement */}
            <Card className="mb-4 border-l-4 border-l-violet-400">
              <CardContent className="py-3">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-violet-600 uppercase tracking-wider mb-1">
                      H7 — Cross-Framework Comparison
                    </p>
                    <p className="text-gray-700 text-sm leading-relaxed">
                      Different AutoML frameworks produce significantly different detection outcomes,
                      validating the need for multi-framework evaluation in the methodology.
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                      Kruskal-Wallis omnibus test + pairwise Mann-Whitney U with Bonferroni correction.
                    </p>
                  </div>
                  <div className="shrink-0">
                    {crossFramework.verdict === "significant_differences" ? (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-green-100 text-green-700 border border-green-200">
                        <ShieldCheck className="w-4 h-4" />
                        Significant Differences
                      </span>
                    ) : crossFramework.verdict === "trending_differences" ? (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-amber-100 text-amber-700 border border-amber-200">
                        <AlertTriangle className="w-4 h-4" />
                        Trending Differences
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold bg-gray-100 text-gray-600 border border-gray-200">
                        <Info className="w-4 h-4" />
                        No Significant Differences
                      </span>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Framework ranking table */}
            {crossFramework.ranking && crossFramework.ranking.length > 0 && (
              <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-700 mb-3">Framework Ranking</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 text-left">
                        <th className="pb-2 pr-4 font-semibold text-gray-600">#</th>
                        <th className="pb-2 pr-4 font-semibold text-gray-600">Framework</th>
                        <th className="pb-2 pr-4 font-semibold text-gray-600 text-right">AUC</th>
                        <th className="pb-2 pr-4 font-semibold text-gray-600 text-right">Avg Detection Rate</th>
                        <th className="pb-2 pr-4 font-semibold text-gray-600 text-right">Iterations</th>
                        <th className="pb-2 pr-4 font-semibold text-gray-600 text-right">Total Duration</th>
                        <th className="pb-2 font-semibold text-gray-600 text-right">Training Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {crossFramework.ranking.map((fw) => (
                        <tr key={fw.framework} className="border-b border-gray-100 hover:bg-violet-50/50 transition-colors">
                          <td className="py-2 pr-4 font-mono text-xs text-gray-500">{fw.rank}</td>
                          <td className="py-2 pr-4 font-semibold text-gray-800">
                            {fw.framework === "h2o" ? "H2O" :
                              fw.framework === "autogluon" ? "AutoGluon" :
                              fw.framework === "pycaret" ? "PyCaret" :
                              fw.framework === "tpot" ? "TPOT" :
                              fw.framework === "autosklearn" ? "auto-sklearn" :
                              fw.framework}
                          </td>
                          <td className="py-2 pr-4 text-right font-bold text-violet-700">
                            {fw.auc != null ? N(fw.auc).toFixed(4) : "--"}
                          </td>
                          <td className="py-2 pr-4 text-right">
                            {fw.mean_detection_rate != null ? `${(N(fw.mean_detection_rate) * 100).toFixed(1)}%` : "--"}
                          </td>
                          <td className="py-2 pr-4 text-right text-gray-600">{fw.n_iterations}</td>
                          <td className="py-2 pr-4 text-right font-mono text-xs text-gray-700">
                            {fw.total_duration_formatted || "--"}
                          </td>
                          <td className="py-2 text-right font-mono text-xs text-gray-700">
                            {fw.training_time_secs != null
                              ? N(fw.training_time_secs) >= 60
                                ? `${(N(fw.training_time_secs) / 60).toFixed(1)} min`
                                : `${N(fw.training_time_secs).toFixed(1)}s`
                              : "--"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Timing comparison chart */}
            {crossFramework.timing && Object.keys(crossFramework.timing).length > 0 && (
              <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-700 mb-3">
                  <Timer className="w-4 h-4 inline mr-1.5 text-amber-500" />
                  Experiment Duration Comparison
                </h4>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Bar chart: total duration per framework */}
                  <div>
                    <h5 className="text-xs font-semibold text-gray-600 mb-2">Total Duration (all modes)</h5>
                    <ResponsiveContainer width="100%" height={240}>
                      <BarChart data={Object.entries(crossFramework.timing).map(([fw, data]) => ({
                        framework: fw === "h2o" ? "H2O" :
                          fw === "autogluon" ? "AutoGluon" :
                          fw === "pycaret" ? "PyCaret" :
                          fw === "tpot" ? "TPOT" :
                          fw === "autosklearn" ? "auto-sklearn" : fw,
                        duration_min: N(data.total_duration_seconds) / 60,
                        experiments: data.total_experiments || 0,
                      }))}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                        <XAxis dataKey="framework" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} label={{ value: "Minutes", angle: -90, position: "insideLeft", offset: 10, fontSize: 10 }} />
                        <Tooltip content={({ active, payload, label }) => {
                          if (!active || !payload?.length) return null;
                          return (
                            <div className="bg-white shadow-lg rounded-lg p-3 text-sm border border-gray-200">
                              <p className="font-semibold text-gray-800 mb-1">{label}</p>
                              <p className="text-violet-600">Duration: {N(payload[0]?.value).toFixed(1)} min</p>
                              {payload[0]?.payload?.experiments && (
                                <p className="text-gray-500 text-xs">{payload[0].payload.experiments} experiment(s)</p>
                              )}
                            </div>
                          );
                        }} />
                        <Bar dataKey="duration_min" name="Duration (min)" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Per-mode breakdown table */}
                  <div>
                    <h5 className="text-xs font-semibold text-gray-600 mb-2">Duration by Simulation Mode</h5>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-gray-200">
                            <th className="pb-1.5 pr-3 text-left font-semibold text-gray-600">Framework</th>
                            <th className="pb-1.5 pr-3 text-right font-semibold text-gray-600">Deterministic</th>
                            <th className="pb-1.5 pr-3 text-right font-semibold text-gray-600">Medium</th>
                            <th className="pb-1.5 text-right font-semibold text-gray-600">Realistic</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(crossFramework.timing).map(([fw, data]) => (
                            <tr key={fw} className="border-b border-gray-100">
                              <td className="py-1.5 pr-3 font-semibold text-gray-800">
                                {fw === "h2o" ? "H2O" :
                                  fw === "autogluon" ? "AutoGluon" :
                                  fw === "pycaret" ? "PyCaret" :
                                  fw === "tpot" ? "TPOT" :
                                  fw === "autosklearn" ? "auto-sklearn" : fw}
                              </td>
                              {["deterministic", "medium", "realistic"].map((mode) => (
                                <td key={mode} className="py-1.5 pr-3 text-right font-mono text-gray-700">
                                  {data.modes?.[mode]?.duration_formatted || "--"}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Kruskal-Wallis + pairwise tests */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Kruskal-Wallis */}
              {crossFramework.kruskal_wallis && (
                <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                  <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                    Kruskal-Wallis Omnibus Test
                  </h5>
                  <div className="flex items-baseline gap-2">
                    <span className="text-xl font-bold text-gray-800">
                      H = {N(crossFramework.kruskal_wallis.h_statistic).toFixed(3)}
                    </span>
                    <span className="text-xs text-gray-500">
                      p = {N(crossFramework.kruskal_wallis.p_value).toExponential(2)}
                    </span>
                    {crossFramework.kruskal_wallis.significant && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                        Significant
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Tests whether detection rate distributions differ across {crossFramework.n_frameworks} frameworks
                  </p>
                </div>
              )}

              {/* Pairwise comparisons */}
              {crossFramework.pairwise_tests && crossFramework.pairwise_tests.length > 0 && (
                <div className="rounded-xl bg-gray-50 p-4 border border-gray-200">
                  <h5 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                    Pairwise Mann-Whitney U (Bonferroni)
                  </h5>
                  <div className="space-y-1.5 max-h-64 overflow-y-auto">
                    {crossFramework.pairwise_tests.map((pw, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm flex-wrap">
                        <span className="text-gray-600 font-mono text-xs min-w-[140px]">
                          {pw.better === pw.framework_a ? (
                            <><strong className="text-gray-800">{pw.framework_a}</strong> vs {pw.framework_b}</>
                          ) : pw.better === pw.framework_b ? (
                            <>{pw.framework_a} vs <strong className="text-gray-800">{pw.framework_b}</strong></>
                          ) : (
                            <>{pw.framework_a} vs {pw.framework_b}</>
                          )}
                        </span>
                        {pw.mann_whitney_u != null && (
                          <span className="text-xs text-gray-400 font-mono">
                            U={N(pw.mann_whitney_u).toFixed(0)}
                          </span>
                        )}
                        {pw.mean_a != null && pw.mean_b != null && (
                          <span className="text-xs text-gray-500 font-mono">
                            {N(pw.mean_a).toFixed(3)} vs {N(pw.mean_b).toFixed(3)}
                          </span>
                        )}
                        <span className="text-xs text-gray-500 font-mono">
                          p={pw.bonferroni_p != null ? N(pw.bonferroni_p).toExponential(2) : "--"}
                        </span>
                        {pw.significant_corrected ? (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 font-medium">
                            sig ({pw.effect_size})
                          </span>
                        ) : (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                            n.s.
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Noise dominance note */}
            {crossFramework.noise_dominance_note && (
              <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                  <p className="text-xs text-amber-700">{crossFramework.noise_dominance_note}</p>
                </div>
              </div>
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* Framework x Mode Interaction Analysis                             */}
      {/* ================================================================= */}
      <Section title="Framework x Mode Interaction" icon={GitCompare} loading={sectionLoading.frameworkInteraction}>
        {!frameworkInteraction || frameworkInteraction.status !== "ok" ? (
          <div className="flex flex-col items-center justify-center py-8 text-gray-500">
            <Info className="w-6 h-6 mb-2" />
            <p className="text-sm">{frameworkInteraction?.message || "Need data from multiple frameworks and modes."}</p>
          </div>
        ) : (
          <>
            <Card className="mb-4 border-l-4 border-l-indigo-400">
              <CardContent className="py-3">
                <p className="text-sm text-gray-700 leading-relaxed">{frameworkInteraction.conclusion}</p>
              </CardContent>
            </Card>

            {/* Variance decomposition */}
            <h4 className="text-sm font-semibold text-gray-600 mb-3">Variance Decomposition (eta-squared)</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              {["framework", "simulation_mode", "interaction", "residual"].map((factor) => {
                const d = frameworkInteraction.variance_decomposition?.[factor];
                if (!d) return null;
                const label = factor === "simulation_mode" ? "Mode" : factor.charAt(0).toUpperCase() + factor.slice(1);
                return (
                  <div key={factor} className="rounded-xl bg-gray-50 p-3 border border-gray-200 text-center">
                    <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">{label}</h5>
                    <span className="text-lg font-bold text-gray-800">{N(d.eta_squared).toFixed(3)}</span>
                    {d.interpretation && (
                      <p className="text-xs text-gray-500 mt-0.5">{d.interpretation}</p>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Per-mode significance */}
            <h4 className="text-sm font-semibold text-gray-600 mb-3">Per-Mode Framework Significance</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {Object.entries(frameworkInteraction.per_mode_framework_significance || {}).map(([mode, d]) => (
                <div key={mode} className={`rounded-xl p-3 border ${d.significant ? "bg-green-50 border-green-200" : "bg-gray-50 border-gray-200"}`}>
                  <h5 className="text-xs font-semibold uppercase mb-1">{mode}</h5>
                  {d.error ? (
                    <p className="text-xs text-gray-400">{d.error}</p>
                  ) : (
                    <>
                      <p className="text-sm font-mono">H={N(d.kruskal_h).toFixed(2)}, p={N(d.p_value).toFixed(4)}</p>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${d.significant ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                        {d.significant ? "Significant" : "Not significant"}
                      </span>
                    </>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H8 — Temporal Predictive Validity                                 */}
      {/* ================================================================= */}
      <Section title="H8 — Temporal Predictive Validity" icon={Clock} loading={sectionLoading.temporalValidation}>
        {!temporalValidation || temporalValidation.status === "no_temporal_data" ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">{temporalValidation?.message || "No temporal validation data available."}</p>
            <p className="text-xs mt-1">Run experiments with temporal_training=True to generate held-out metrics.</p>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4">
              <h4 className="text-base font-semibold text-gray-800">
                H8 — Temporal Predictive Validity
              </h4>
              {temporalValidation.verdict === "supported" ? (
                <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-xs font-medium">Supported</span>
              ) : temporalValidation.verdict === "trending" ? (
                <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-xs font-medium">Trending</span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-xs font-medium">Not Supported</span>
              )}
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Does the model genuinely predict outcomes on unseen iterations? Evaluated via expanding-window train/test split.
            </p>

            {/* Summary stats */}
            {temporalValidation.summary && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <div className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Mean Held-Out AUC</p>
                  <p className="text-lg font-bold text-gray-900">{temporalValidation.summary.mean_auc != null ? N(temporalValidation.summary.mean_auc).toFixed(3) : "--"}</p>
                </div>
                <div className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Mean Brier Score</p>
                  <p className="text-lg font-bold text-gray-900">{temporalValidation.summary.mean_brier != null ? N(temporalValidation.summary.mean_brier).toFixed(4) : "--"}</p>
                </div>
                <div className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Mean ECE</p>
                  <p className="text-lg font-bold text-gray-900">{temporalValidation.summary.mean_ece != null ? N(temporalValidation.summary.mean_ece).toFixed(4) : "--"}</p>
                </div>
                <div className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Evaluations</p>
                  <p className="text-lg font-bold text-gray-900">{temporalValidation.summary.n_evaluations ?? "--"}</p>
                </div>
              </div>
            )}

            {/* Temporal AUC progression chart */}
            {temporalValidation.iterations && temporalValidation.iterations.length > 0 && (
              <div>
                <h5 className="text-sm font-semibold text-gray-700 mb-2">Held-Out AUC Over Iterations</h5>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={temporalValidation.iterations.map(it => ({
                    iteration: it.iteration,
                    auc: it.auc_roc,
                    brier: it.brier_score,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="iteration" tick={{ fontSize: 11 }} label={{ value: "Iteration", position: "bottom", offset: -2, fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} domain={[0, 1]} />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend />
                    <ReferenceLine y={0.5} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "Random (0.5)", position: "right", fontSize: 10, fill: "#ef4444" }} />
                    <Line type="monotone" dataKey="auc" name="Held-Out AUC" stroke="#8b5cf6" strokeWidth={2} dot={{ fill: "#8b5cf6", r: 3 }} connectNulls />
                    <Line type="monotone" dataKey="brier" name="Brier Score" stroke="#f97316" strokeWidth={1.5} strokeDasharray="4 3" dot={{ fill: "#f97316", r: 2 }} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* AUC trend */}
            {temporalValidation.summary?.auc_trend && (
              <div className="mt-3 rounded-xl bg-gray-50 p-3 border border-gray-200">
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">AUC Trend (Spearman)</p>
                <p className="text-sm text-gray-700">
                  ρ = {N(temporalValidation.summary.auc_trend.spearman_rho).toFixed(3)},
                  p = {N(temporalValidation.summary.auc_trend.p_value).toExponential(2)}
                  — <strong>{temporalValidation.summary.auc_trend.direction}</strong>
                </p>
              </div>
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H9 — Baseline Comparison                                          */}
      {/* ================================================================= */}
      <Section title="H9 — ML Value Over Baselines" icon={GitCompare} loading={sectionLoading.baselineComparison}>
        {!baselineComparison || baselineComparison.status === "insufficient_data" ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">{baselineComparison?.message || "No baseline comparison data available."}</p>
            <p className="text-xs mt-1">Run baseline experiments (random, CVSS, round-robin, no-ML) to compare.</p>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4">
              <h4 className="text-base font-semibold text-gray-800">
                H9 — ML Value Over Baselines
              </h4>
              {baselineComparison.verdict === "supported" ? (
                <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-xs font-medium">ML Wins</span>
              ) : baselineComparison.verdict === "trending" ? (
                <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-xs font-medium">Slight Edge</span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-xs font-medium">No Advantage</span>
              )}
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Compares ML-guided test selection against non-ML baselines (random, CVSS-priority, round-robin, exhaustive).
            </p>

            {/* Strategy comparison table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 px-3 text-xs font-semibold text-gray-600">Strategy</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600">Mean Det. Rate</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600">Std Dev</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600">Iterations</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600">Lift vs ML</th>
                    <th className="text-center py-2 px-3 text-xs font-semibold text-gray-600">Sig?</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(baselineComparison.strategies || {}).map(([name, data]) => (
                    <tr key={name} className={`border-b border-gray-100 ${name === "ml_guided" ? "bg-blue-50 font-medium" : ""}`}>
                      <td className="py-2 px-3 font-medium text-gray-800">{name === "ml_guided" ? "ML-Guided" : name.replace("_", " ")}</td>
                      <td className="text-right py-2 px-3">{data.mean_rate != null ? (N(data.mean_rate) * 100).toFixed(1) + "%" : "--"}</td>
                      <td className="text-right py-2 px-3 text-gray-500">{data.std_rate != null ? N(data.std_rate).toFixed(3) : "--"}</td>
                      <td className="text-right py-2 px-3">{data.n_iterations ?? "--"}</td>
                      <td className="text-right py-2 px-3">{data.lift_vs_ml != null ? `${data.lift_vs_ml > 0 ? "+" : ""}${N(data.lift_vs_ml).toFixed(1)}%` : "--"}</td>
                      <td className="text-center py-2 px-3">
                        {data.vs_ml_test?.significant ? (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700">sig</span>
                        ) : data.vs_ml_test ? (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">n.s.</span>
                        ) : "--"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H11 — Cross-Protocol Generalization (LOPO)                        */}
      {/* ================================================================= */}
      <Section title="H11 — Cross-Protocol Generalization" icon={Globe} loading={sectionLoading.generalization}>
        {!generalization || generalization.status === "insufficient_data" ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">{generalization?.message || "No generalization data available."}</p>
            <p className="text-xs mt-1">LOPO analysis runs after experiments complete. Check experiment data availability.</p>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4">
              <h4 className="text-base font-semibold text-gray-800">
                H11 — Leave-One-Protocol-Out Generalization
              </h4>
              {generalization.verdict === "generalizes" ? (
                <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-xs font-medium">Generalizes</span>
              ) : generalization.verdict === "partial_generalization" ? (
                <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-xs font-medium">Partial</span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-xs font-medium">Does Not Generalize</span>
              )}
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Tests whether the model can predict vulnerabilities on protocols it has never seen during training.
            </p>

            {/* LOPO summary */}
            {generalization.summary && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <div className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Mean LOPO AUC</p>
                  <p className="text-lg font-bold text-gray-900">{generalization.summary.mean_auc != null ? N(generalization.summary.mean_auc).toFixed(3) : "--"}</p>
                </div>
                <div className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Min / Max AUC</p>
                  <p className="text-lg font-bold text-gray-900">
                    {generalization.summary.min_auc != null ? N(generalization.summary.min_auc).toFixed(3) : "--"} / {generalization.summary.max_auc != null ? N(generalization.summary.max_auc).toFixed(3) : "--"}
                  </p>
                </div>
                <div className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Mean Brier</p>
                  <p className="text-lg font-bold text-gray-900">{generalization.summary.mean_brier != null ? N(generalization.summary.mean_brier).toFixed(4) : "--"}</p>
                </div>
                <div className="rounded-xl bg-gray-50 p-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">Protocols Evaluated</p>
                  <p className="text-lg font-bold text-gray-900">{generalization.summary.n_evaluated ?? 0} / {generalization.summary.n_protocols ?? 0}</p>
                </div>
              </div>
            )}

            {/* Per-protocol table */}
            {generalization.protocols && generalization.protocols.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 px-3 text-xs font-semibold text-gray-600">Held-Out Protocol</th>
                      <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600">AUC</th>
                      <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600">Brier</th>
                      <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600">ECE</th>
                      <th className="text-right py-2 px-3 text-xs font-semibold text-gray-600">Train/Test Size</th>
                      <th className="text-center py-2 px-3 text-xs font-semibold text-gray-600">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {generalization.protocols.map((p) => (
                      <tr key={p.protocol} className="border-b border-gray-100">
                        <td className="py-2 px-3 font-medium text-gray-800">{p.protocol}</td>
                        <td className="text-right py-2 px-3">{p.auc_roc != null ? N(p.auc_roc).toFixed(3) : "--"}</td>
                        <td className="text-right py-2 px-3">{p.brier_score != null ? N(p.brier_score).toFixed(4) : "--"}</td>
                        <td className="text-right py-2 px-3">{p.ece != null ? N(p.ece).toFixed(4) : "--"}</td>
                        <td className="text-right py-2 px-3 text-gray-500">{p.n_train ?? "--"} / {p.n_test ?? "--"}</td>
                        <td className="text-center py-2 px-3">
                          {p.status === "ok" ? (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700">ok</span>
                          ) : (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{p.status}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* H10 — LLM Generation Effectiveness                               */}
      {/* ================================================================= */}
      <Section title="H10 — LLM Generation Effectiveness" icon={Sparkles} loading={sectionLoading.llmEffectiveness}>
        {!llmEffectiveness || llmEffectiveness.status !== "ok" ? (
          <div className="flex flex-col items-center justify-center py-8 text-gray-500">
            <Info className="w-6 h-6 mb-2" />
            <p className="text-sm">{llmEffectiveness?.message || "No LLM test data available yet."}</p>
          </div>
        ) : (
          <>
            <Card className="mb-4 border-l-4 border-l-pink-400">
              <CardContent className="py-3">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-pink-600 uppercase tracking-wider mb-1">
                      H10 — LLM Generation Effectiveness
                    </p>
                    <p className="text-gray-700 text-sm leading-relaxed">
                      LLM-generated tests find additional vulnerabilities beyond the static registry.
                    </p>
                  </div>
                  <VerdictBadge verdict={llmEffectiveness.verdict} />
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              {/* Primary: unique vulnerability type coverage */}
              <div className="rounded-xl bg-blue-50 p-3 border border-blue-200 text-center">
                <h5 className="text-xs font-semibold text-blue-600 uppercase mb-1">Registry Coverage</h5>
                <span className="text-lg font-bold">
                  {llmEffectiveness.registry?.unique_vuln_types ?? "--"}
                  <span className="text-sm font-normal text-gray-500 ml-1">types</span>
                </span>
                <p className="text-xs text-gray-500 mt-0.5">
                  {llmEffectiveness.registry?.n_vulns} vulns · {(N(llmEffectiveness.registry?.detection_rate) * 100).toFixed(1)}% hit rate
                </p>
              </div>
              <div className="rounded-xl bg-pink-50 p-3 border border-pink-200 text-center">
                <h5 className="text-xs font-semibold text-pink-600 uppercase mb-1">LLM Coverage</h5>
                <span className="text-lg font-bold">
                  {llmEffectiveness.llm?.unique_vuln_types ?? "--"}
                  <span className="text-sm font-normal text-gray-500 ml-1">types</span>
                </span>
                <p className="text-xs text-gray-500 mt-0.5">
                  {llmEffectiveness.llm?.n_vulns} vulns · {(N(llmEffectiveness.llm?.detection_rate) * 100).toFixed(1)}% hit rate
                </p>
              </div>
              {/* LLM-exclusive attack categories — the key H10 signal */}
              <div className="rounded-xl bg-teal-50 p-3 border border-teal-300 text-center">
                <h5 className="text-xs font-semibold text-teal-600 uppercase mb-1">Exclusive to LLM</h5>
                <span className="text-lg font-bold text-teal-700">
                  {llmEffectiveness.llm_exclusive_types ?? "--"}
                  <span className="text-sm font-normal text-gray-500 ml-1">novel types</span>
                </span>
                <p className="text-xs text-gray-500 mt-0.5">
                  {llmEffectiveness.llm_exclusive_vulns ?? 0} attack scenarios not in registry
                </p>
              </div>
              {/* Fisher p-value — secondary supporting stat, fixed label bug */}
              <div className="rounded-xl bg-gray-50 p-3 border border-gray-200 text-center">
                <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Fisher p-value</h5>
                <span className="text-lg font-bold font-mono">
                  {llmEffectiveness.fisher_exact?.p_value != null
                    ? (N(llmEffectiveness.fisher_exact.p_value) < 1e-5
                        ? "<1e-5"
                        : N(llmEffectiveness.fisher_exact.p_value).toExponential(2))
                    : "--"}
                </span>
                <p className="text-xs text-gray-400 mt-0.5">
                  {(() => {
                    const pRaw = llmEffectiveness.fisher_exact?.p_value;
                    // Guard: p_value may be null (test failed) or 0 (underflow from rounding)
                    if (pRaw == null) return "Test unavailable";
                    const p = N(pRaw);
                    // p=0 from rounding means extremely significant; treat as < 0.05
                    if (p < 0.05 || pRaw === 0) {
                      const llmHigher = N(llmEffectiveness.llm?.detection_rate) > N(llmEffectiveness.registry?.detection_rate);
                      return llmHigher ? "Sig. — LLM higher hit rate" : "Sig. — registry higher hit rate";
                    }
                    return "Not significant";
                  })()}
                </p>
                {llmEffectiveness.fisher_exact?.odds_ratio != null && (
                  <p className="text-xs text-gray-400">
                    OR: {N(llmEffectiveness.fisher_exact.odds_ratio).toFixed(2)}
                    {llmEffectiveness.fisher_exact?.odds_ratio_ci_95 &&
                      ` [${N(llmEffectiveness.fisher_exact.odds_ratio_ci_95[0]).toFixed(2)}, ${N(llmEffectiveness.fisher_exact.odds_ratio_ci_95[1]).toFixed(2)}]`}
                  </p>
                )}
              </div>
            </div>

            <p className="text-xs text-gray-400 px-1 mb-2">
              Coverage = unique vulnerability <em>types</em> found, not detection rate.
              A lower LLM hit rate is expected — LLM probes novel attack surface where vulnerabilities are rarer.
              The key signal is <span className="text-teal-600 font-medium">Exclusive to LLM</span>: attack categories the static registry never tests for.
            </p>

            {llmEffectiveness.llm_exclusive_vulns > 0 && (
              <p className="text-sm text-green-700 bg-green-50 p-2 rounded border border-green-200">
                LLM tests discovered {llmEffectiveness.llm_exclusive_vulns} unique vulnerability instance(s) not found by registry tests
                {llmEffectiveness.llm_exclusive_types > 0 && `, across ${llmEffectiveness.llm_exclusive_types} novel attack category(s) the registry has no coverage for`}.
              </p>
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* Ablation Analysis                                                 */}
      {/* ================================================================= */}
      <Section title="Ablation Analysis" icon={Layers} loading={sectionLoading.ablation}>
        {!ablation || ablation.status !== "ok" ? (
          <div className="flex flex-col items-center justify-center py-8 text-gray-500">
            <Info className="w-6 h-6 mb-2" />
            <p className="text-sm">{ablation?.message || "Ablation data not yet available."}</p>
            <p className="text-xs mt-1">Requires baseline + ML + LLM experiments to compute marginal contributions.</p>
          </div>
        ) : (
          <>
            <Card className="mb-4 border-l-4 border-l-teal-400">
              <CardContent className="py-3">
                <p className="text-sm font-semibold text-teal-600 uppercase tracking-wider mb-1">
                  Component Ablation
                </p>
                <p className="text-gray-700 text-sm leading-relaxed">
                  Marginal contribution of each system component, from random baseline to full ML+LLM system.{" "}
                  <span className="font-semibold text-teal-700">Coverage Lift</span> (unique vulnerability types) is the
                  primary metric for LLM contribution — detection rate rewards exploitation efficiency but penalises
                  coverage-seeking behaviour. ML alone maximises detection rate by repeatedly targeting known patterns;
                  LLM breaks this loop by discovering novel attack classes.
                </p>
              </CardContent>
            </Card>

            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Condition</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Det. Rate</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Tests</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Vulns</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Unique Types</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-teal-600 uppercase">Coverage Lift</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-400 uppercase">vs Baseline</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-400 uppercase">Efficiency Lift</th>
                  </tr>
                </thead>
                <tbody>
                  {(ablation.conditions || []).map((c, i) => (
                    <tr key={c.key} className={`border-b border-gray-100 ${
                      c.key === "phase5" || c.key === "phase6"
                        ? "bg-blue-50/60 border-l-2 border-l-blue-400"
                        : c.key === "ml_llm"
                        ? "bg-teal-50/40 border-l-2 border-l-teal-400"
                        : i % 2 === 0 ? "bg-gray-50/50" : ""
                    }`}>
                      <td className="py-2 px-3 font-medium">{c.condition}</td>
                      <td className="py-2 px-3 text-right font-mono text-gray-500">{(N(c.detection_rate) * 100).toFixed(1)}%</td>
                      <td className="py-2 px-3 text-right text-gray-500">{c.n_tests}</td>
                      <td className="py-2 px-3 text-right text-gray-500">{c.n_vulns}</td>
                      <td className="py-2 px-3 text-right font-semibold">{c.unique_vuln_types}</td>
                      {/* PRIMARY: sequential coverage lift vs previous condition */}
                      <td className="py-2 px-3 text-right">
                        {c.coverage_lift_pct != null && c.coverage_lift_pct !== 0 ? (
                          <span className={`font-semibold ${c.coverage_lift_pct > 0 ? "text-teal-600" : "text-orange-500"}`}>
                            {c.coverage_lift_pct > 0 ? "+" : ""}{N(c.coverage_lift_pct).toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-gray-400">baseline</span>
                        )}
                      </td>
                      {/* SECONDARY: absolute coverage lift vs random baseline */}
                      <td className="py-2 px-3 text-right text-xs">
                        {c.coverage_lift_vs_baseline_pct != null && c.coverage_lift_vs_baseline_pct !== 0 ? (
                          <span className={c.coverage_lift_vs_baseline_pct > 0 ? "text-teal-500" : "text-orange-400"}>
                            {c.coverage_lift_vs_baseline_pct > 0 ? "+" : ""}{N(c.coverage_lift_vs_baseline_pct).toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      {/* TERTIARY: efficiency lift (detection rate, de-emphasised) */}
                      <td className="py-2 px-3 text-right text-xs text-gray-400">
                        {c.marginal_lift_pct != null && c.marginal_lift_pct !== 0 ? (
                          <span className={c.marginal_lift_pct > 0 ? "text-green-500" : "text-red-400"}>
                            {c.marginal_lift_pct > 0 ? "+" : ""}{N(c.marginal_lift_pct).toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="text-xs text-gray-400 mt-2 px-1">
              Coverage Lift: sequential % change in unique vulnerability types vs previous condition.
              vs Baseline: absolute % change vs Random Selection.
              Efficiency Lift: detection rate change (vulns/tests) — de-emphasised as it penalises coverage-seeking.
            </p>
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* Phase Comparison — 2×2 Factorial (Dynamic Features)              */}
      {/* ================================================================= */}
      <Section title="Phase Comparison: Static vs Dynamic Features" icon={Layers} loading={sectionLoading.dynamicComparison}>
        {!dynamicComparison || dynamicComparison.verdict === "insufficient_data" ? (
          <div className="flex flex-col items-center justify-center py-8 text-gray-500">
            <Info className="w-6 h-6 mb-2" />
            <p className="text-sm font-medium">Awaiting Phase 5 &amp; 6 data</p>
            <p className="text-xs mt-1">
              Run experiments with <code className="bg-gray-100 px-1 rounded">--only-phase5</code> or{" "}
              <code className="bg-gray-100 px-1 rounded">--only-phase6</code> to populate this comparison.
            </p>
            {dynamicComparison?.phases?.framework?.mean_detection != null && (
              <p className="text-xs mt-2 text-blue-600">
                Phase 1 (Static/No-LLM) baseline: {(dynamicComparison.phases.framework.mean_detection * 100).toFixed(1)}%
              </p>
            )}
          </div>
        ) : (
          <>
            <Card className="mb-4 border-l-4 border-l-blue-400">
              <CardContent className="py-3">
                <p className="text-sm font-semibold text-blue-600 uppercase tracking-wider mb-1">
                  2×2 Factorial: Feature Type × LLM
                </p>
                <p className="text-gray-700 text-sm leading-relaxed">
                  Interaction term quantifies whether dynamic features amplify LLM value:{" "}
                  <span className="font-mono">(P6−P5) − (P3−P1)</span>
                </p>
              </CardContent>
            </Card>

            {/* 2×2 table */}
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b-2 border-gray-200">
                    <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Features</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">No LLM</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">With LLM</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">LLM Effect</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const ft = dynamicComparison.factorial_table || {};
                    const fmtPct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : "—";
                    const fmtDiff = (v) => v != null
                      ? <span className={v > 0 ? "text-green-600 font-semibold" : v < 0 ? "text-red-600" : "text-gray-500"}>
                          {v > 0 ? "+" : ""}{(v * 100).toFixed(1)}pp
                        </span>
                      : <span className="text-gray-400">—</span>;
                    const llmEffect_static = ft.static_llm != null && ft.static_no_llm != null
                      ? ft.static_llm - ft.static_no_llm : null;
                    const llmEffect_dynamic = ft.dynamic_llm != null && ft.dynamic_no_llm != null
                      ? ft.dynamic_llm - ft.dynamic_no_llm : null;
                    return (
                      <>
                        <tr className="border-b border-gray-100 bg-gray-50/50">
                          <td className="py-2 px-3 font-medium">Static (P1 / P3)</td>
                          <td className="py-2 px-3 text-right font-mono">{fmtPct(ft.static_no_llm)}</td>
                          <td className="py-2 px-3 text-right font-mono">{fmtPct(ft.static_llm)}</td>
                          <td className="py-2 px-3 text-right">{fmtDiff(llmEffect_static)}</td>
                        </tr>
                        <tr className="border-b border-gray-100 bg-blue-50/40">
                          <td className="py-2 px-3 font-medium text-blue-700">Dynamic (P5 / P6)</td>
                          <td className="py-2 px-3 text-right font-mono">{fmtPct(ft.dynamic_no_llm)}</td>
                          <td className="py-2 px-3 text-right font-mono">{fmtPct(ft.dynamic_llm)}</td>
                          <td className="py-2 px-3 text-right">{fmtDiff(llmEffect_dynamic)}</td>
                        </tr>
                        <tr className="border-t-2 border-gray-200 bg-gray-100/70">
                          <td className="py-2 px-3 font-semibold text-gray-600">Dynamic Main Effect</td>
                          <td className="py-2 px-3 text-right">{fmtDiff(ft.dynamic_main_effect)}</td>
                          <td className="py-2 px-3 text-right"></td>
                          <td className="py-2 px-3 text-right font-semibold">
                            Interaction: {ft.interaction != null
                              ? <span className={Math.abs(ft.interaction) > 0.01 ? "text-purple-700" : "text-gray-500"}>
                                  {ft.interaction > 0 ? "+" : ""}{(ft.interaction * 100).toFixed(1)}pp
                                </span>
                              : <span className="text-gray-400">—</span>
                            }
                          </td>
                        </tr>
                      </>
                    );
                  })()}
                </tbody>
              </table>
            </div>

            {/* Statistical tests */}
            {dynamicComparison.statistical_tests && (
              <div className="flex gap-4 flex-wrap text-xs text-gray-600">
                {dynamicComparison.statistical_tests.p1_vs_p5 && (
                  <span>
                    P1 vs P5 (Mann-Whitney): p={dynamicComparison.statistical_tests.p1_vs_p5.p_value}
                    {dynamicComparison.statistical_tests.p1_vs_p5.p_value < 0.05
                      ? <span className="text-green-600 ml-1">✓ sig.</span>
                      : <span className="text-gray-400 ml-1">n.s.</span>}
                  </span>
                )}
                {dynamicComparison.statistical_tests.p3_vs_p6 && (
                  <span>
                    P3 vs P6 (Mann-Whitney): p={dynamicComparison.statistical_tests.p3_vs_p6.p_value}
                    {dynamicComparison.statistical_tests.p3_vs_p6.p_value < 0.05
                      ? <span className="text-green-600 ml-1">✓ sig.</span>
                      : <span className="text-gray-400 ml-1">n.s.</span>}
                  </span>
                )}
              </div>
            )}
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* Hypothesis Synthesis Summary                                      */}
      {/* ================================================================= */}
      <Section title="Hypothesis Synthesis" icon={FileText} defaultOpen loading={sectionLoading.synthesis}>
        {!synthesis || !synthesis.hypotheses ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500">
            <Info className="w-8 h-8 mb-2 text-gray-500" />
            <p className="text-sm">No synthesis data available.</p>
            <p className="text-xs mt-1">Run experiments to generate hypothesis test results.</p>
          </div>
        ) : (
          <>
            {/* Overall strength badge */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-sm text-gray-600">
                  {synthesis.summary.supported} supported, {synthesis.summary.trending} trending, {synthesis.summary.not_supported} not supported
                  {synthesis.summary.errors_or_insufficient > 0 && `, ${synthesis.summary.errors_or_insufficient} insufficient data`}
                </p>
              </div>
              <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold border ${
                synthesis.summary.overall_strength === "strong"
                  ? "bg-green-100 text-green-700 border-green-200"
                  : synthesis.summary.overall_strength === "moderate"
                  ? "bg-amber-100 text-amber-700 border-amber-200"
                  : synthesis.summary.overall_strength === "weak"
                  ? "bg-orange-100 text-orange-700 border-orange-200"
                  : "bg-gray-100 text-gray-600 border-gray-200"
              }`}>
                {synthesis.summary.overall_strength === "strong" && <CheckCircle2 className="w-4 h-4" />}
                {synthesis.summary.overall_strength === "moderate" && <AlertTriangle className="w-4 h-4" />}
                {synthesis.summary.overall_strength === "weak" && <Info className="w-4 h-4" />}
                Overall: {synthesis.summary.overall_strength}
              </span>
            </div>

            {/* Synthesis table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b-2 border-gray-300 text-left">
                    <th className="pb-2 pr-3 font-semibold text-gray-700">ID</th>
                    <th className="pb-2 pr-3 font-semibold text-gray-700">Hypothesis</th>
                    <th className="pb-2 pr-3 font-semibold text-gray-700">Test</th>
                    <th className="pb-2 pr-3 font-semibold text-gray-700 text-right">Key Metric</th>
                    <th className="pb-2 pr-3 font-semibold text-gray-700 text-right">p-value</th>
                    <th className="pb-2 pr-3 font-semibold text-gray-700 text-right">
                      Corrected p
                      <span className="block text-[9px] font-normal text-gray-400">Holm-Bonferroni</span>
                    </th>
                    <th className="pb-2 pr-3 font-semibold text-gray-700 text-right">Effect Size</th>
                    <th className="pb-2 font-semibold text-gray-700 text-center">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {synthesis.hypotheses.map((h) => (
                    <tr key={h.id} className="border-b border-gray-100 hover:bg-amber-50/30 transition-colors">
                      <td className="py-2.5 pr-3 font-mono font-bold text-xs text-indigo-600">{h.id}</td>
                      <td className="py-2.5 pr-3 text-gray-800 max-w-xs">
                        <span className="font-medium">{h.name}</span>
                        {h.description && (
                          <p className="text-[10px] text-gray-500 mt-0.5 leading-tight">{h.description}</p>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-gray-600 max-w-[160px]">{h.test_used || "--"}</td>
                      <td className="py-2.5 pr-3 text-right font-mono text-xs text-gray-800">{h.key_metric || "--"}</td>
                      <td className="py-2.5 pr-3 text-right font-mono text-xs">
                        {h.p_value != null ? (
                          <span className={N(h.p_value) < 0.05 ? "text-green-700 font-semibold" : "text-gray-600"}>
                            {N(h.p_value).toExponential(2)}
                          </span>
                        ) : "--"}
                      </td>
                      <td className="py-2.5 pr-3 text-right font-mono text-xs">
                        {h.corrected_p_value != null ? (
                          <span className={h.significant_after_correction ? "text-green-700 font-semibold" : "text-gray-600"}>
                            {N(h.corrected_p_value).toExponential(2)}
                            {h.significant_after_correction === false && h.p_value != null && N(h.p_value) < 0.05 && (
                              <span className="ml-1 text-[9px] text-amber-600" title="Significant before correction but not after">&#x26A0;</span>
                            )}
                          </span>
                        ) : "--"}
                      </td>
                      <td className="py-2.5 pr-3 text-right text-xs">
                        {h.effect_size != null ? (
                          <span className="font-mono text-gray-800">
                            {typeof h.effect_size === "number" ? h.effect_size.toFixed(4) : h.effect_size}
                            {h.effect_interpretation && (
                              <span className="ml-1 text-[10px] text-gray-500">({h.effect_interpretation})</span>
                            )}
                          </span>
                        ) : "--"}
                      </td>
                      <td className="py-2.5 text-center">
                        {h.verdict === "supported" || h.verdict === "efficient" || h.verdict === "significant_differences" || h.verdict === "well_calibrated" || h.verdict === "generalizes" ? (
                          <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-green-100 text-green-700">
                            Supported
                          </span>
                        ) : h.verdict === "trending" || h.verdict === "trending_differences" || h.verdict === "comparable" || h.verdict === "moderately_calibrated" || h.verdict === "partial_generalization" ? (
                          <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-700">
                            Trending
                          </span>
                        ) : h.verdict === "error" || h.verdict === "insufficient_data" ? (
                          <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-500">
                            N/A
                          </span>
                        ) : (
                          <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 text-red-700">
                            Not Supported
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Multiple comparison correction summary */}
            {synthesis.summary?.correction_method && (
              <div className="mt-4 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200">
                <p className="text-xs text-amber-800">
                  <strong>Multiple comparison correction:</strong>{" "}
                  {synthesis.summary.correction_method === "holm_bonferroni" ? "Holm-Bonferroni" : synthesis.summary.correction_method}{" "}
                  applied across {synthesis.summary.n_tests_corrected} tests at family-wise &#x3B1; = {synthesis.summary.family_wise_alpha}.{" "}
                  After correction: <strong>{synthesis.summary.corrected_significant}</strong> significant,{" "}
                  <strong>{synthesis.summary.corrected_not_significant}</strong> not significant.
                  {synthesis.summary.corrected_significant < synthesis.summary.supported && (
                    <span className="ml-1">
                      ({synthesis.summary.supported - synthesis.summary.corrected_significant} hypothesis(es) lost significance after correction — marked with &#x26A0; above.)
                    </span>
                  )}
                </p>
              </div>
            )}

            {/* Thesis-friendly note */}
            <div className="mt-4 px-3 py-2 rounded-lg bg-indigo-50 border border-indigo-200">
              <p className="text-xs text-indigo-700">
                <strong>Thesis note:</strong> This synthesis table summarizes all hypothesis tests for
                {" "}{synthesis.simulation_mode || "all"} simulation mode with {synthesis.automl_tool || "all"} AutoML framework.
                Verdicts are based on p &lt; 0.05 significance threshold with appropriate effect size measures.
                The "Corrected p" column applies Holm-Bonferroni correction to control the family-wise error rate across all {synthesis.summary?.n_tests_corrected || "N"} hypotheses.
                Change the Simulation Mode and AutoML Framework filters above to generate per-condition tables.
              </p>
            </div>
          </>
        )}
      </Section>

      {/* ================================================================= */}
      {/* Iteration Details Table                                           */}
      {/* ================================================================= */}
      <Section title="Iteration Details" icon={Activity} defaultOpen={false} loading={sectionLoading.iterationMetrics}>
        {iterData.length === 0 ? (
          <div className="text-center py-8 text-gray-500 text-sm">
            No iteration data available.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th className="pb-3 pr-4 font-semibold text-gray-600">#</th>
                  <th className="pb-3 pr-4 font-semibold text-gray-600">Experiment</th>
                  <th className="pb-3 pr-4 font-semibold text-gray-600 text-right">Tests</th>
                  <th className="pb-3 pr-4 font-semibold text-gray-600 text-right">Vulns</th>
                  <th className="pb-3 pr-4 font-semibold text-gray-600 text-right">
                    Detection Rate
                  </th>
                  <th className="pb-3 pr-4 font-semibold text-gray-600 text-right">Protocols</th>
                  <th className="pb-3 font-semibold text-gray-600 text-right">Avg Time (ms)</th>
                </tr>
              </thead>
              <tbody>
                {iterData.map((row, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-gray-100 hover:bg-amber-50/50 transition-colors"
                  >
                    <td className="py-2.5 pr-4 font-mono text-xs text-gray-500">
                      {row.iteration}
                    </td>
                    <td className="py-2.5 pr-4 text-gray-700 text-xs font-mono">
                      {row.label}
                    </td>
                    <td className="py-2.5 pr-4 text-right font-medium">{row.total_tests}</td>
                    <td className="py-2.5 pr-4 text-right font-medium text-red-600">
                      {row.total_vulns}
                    </td>
                    <td className="py-2.5 pr-4 text-right">
                      <span
                        className={`font-semibold ${
                          N(row.detection_rate) > 50
                            ? "text-green-600"
                            : N(row.detection_rate) > 20
                            ? "text-amber-600"
                            : "text-gray-600"
                        }`}
                      >
                        {N(row.detection_rate).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-right">{row.unique_protocols ?? 0}</td>
                    <td className="py-2.5 text-right text-gray-500">
                      {N(row.avg_exec_ms).toFixed(0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
