import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Card, CardHeader, CardContent } from "./ui/card";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  FlaskConical,
  Bug,
  ShieldAlert,
  Network,
  RefreshCw,
  ChevronLeft,
  ChevronDown,
  ChevronUp,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Server,
  Timer,
  ArrowUpDown,
  Filter,
  Search,
  AlertTriangle,
  Shield,
  Zap,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Protocol-specific colors
// ---------------------------------------------------------------------------
const PROTOCOL_COLORS = {
  http: "#22c55e",
  mqtt: "#ec4899",
  ssh: "#a855f7",
  ftp: "#eab308",
  telnet: "#ef4444",
  coap: "#06b6d4",
  modbus: "#f97316",
  dns: "#6366f1",
};

const PROTOCOL_BG = {
  http: "bg-green-100 text-green-700",
  mqtt: "bg-pink-100 text-pink-700",
  ssh: "bg-purple-100 text-purple-700",
  ftp: "bg-yellow-100 text-yellow-800",
  telnet: "bg-red-100 text-red-700",
  coap: "bg-cyan-100 text-cyan-700",
  modbus: "bg-orange-100 text-orange-700",
  dns: "bg-indigo-100 text-indigo-700",
};

const SEVERITY_COLORS = {
  critical: "#dc2626",
  high: "#f97316",
  medium: "#eab308",
  low: "#3b82f6",
  info: "#6b7280",
};

const SEVERITY_BG = {
  critical: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-blue-100 text-blue-700",
  info: "bg-gray-100 text-gray-600",
};

const SEVERITY_PALETTE = ["#dc2626", "#f97316", "#eab308", "#3b82f6", "#6b7280"];

const BLUE_PALETTE = [
  "#3b82f6", "#2563eb", "#1d4ed8", "#60a5fa", "#93c5fd",
  "#1e40af", "#3730a3", "#6366f1", "#818cf8", "#a5b4fc",
];

// ---------------------------------------------------------------------------
// KPI definitions for aggregate view
// ---------------------------------------------------------------------------
const KPI_DEFS = [
  { key: "total_tests", label: "Unique Tests", icon: FlaskConical, color: "text-blue-500", format: (v) => v != null ? v.toLocaleString() : "--" },
  { key: "total_vulns", label: "Unique Vulnerabilities", icon: Bug, color: "text-red-500", format: (v) => v != null ? v.toLocaleString() : "--" },
  { key: "detection_rate", label: "Detection Rate", icon: ShieldAlert, color: "text-orange-500", format: (v) => v != null ? `${(Number(v) * 100).toFixed(1)}%` : "--" },
  { key: "protocols_tested", label: "Protocols Tested", icon: Network, color: "text-purple-500", format: (v) => v != null ? v : "--" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getProtocolColor(protocol) {
  return PROTOCOL_COLORS[(protocol || "").toLowerCase()] || BLUE_PALETTE[0];
}

function protocolBadge(proto) {
  const cls = PROTOCOL_BG[(proto || "").toLowerCase()] || "bg-gray-100 text-gray-600";
  return (
    <span key={proto} className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
      {proto}
    </span>
  );
}

function severityBadge(severity) {
  const cls = SEVERITY_BG[(severity || "").toLowerCase()] || "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold capitalize ${cls}`}>
      {severity || "unknown"}
    </span>
  );
}

function formatDate(raw) {
  if (!raw) return "--";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

function formatDuration(ms) {
  if (ms == null || ms === 0) return "--";
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

function statusBadge(status) {
  const s = (status || "").toLowerCase();
  if (s === "completed" || s === "done" || s === "success") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
        <CheckCircle2 className="w-3 h-3" /> {status}
      </span>
    );
  }
  if (s === "failed" || s === "error") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
        <XCircle className="w-3 h-3" /> {status}
      </span>
    );
  }
  if (s === "running" || s === "in_progress") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
        <Loader2 className="w-3 h-3 animate-spin" /> {status}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
      {status || "--"}
    </span>
  );
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-white shadow-lg rounded-lg p-3 text-sm border border-gray-200">
      <p className="font-semibold text-gray-800 mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{ color: entry.color || entry.fill }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Results({ apiUrl, visible = true }) {
  // ----- State: Aggregate data -----
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [vulnsByProtocol, setVulnsByProtocol] = useState([]);
  const [vulnsByType, setVulnsByType] = useState([]);
  const [vulnsByDevice, setVulnsByDevice] = useState([]);
  const [chartsLoading, setChartsLoading] = useState(true);

  // ----- State: Suite results list -----
  const [results, setResults] = useState([]);
  const [resultsLoading, setResultsLoading] = useState(true);

  // ----- State: Selected suite detail -----
  const [selectedResult, setSelectedResult] = useState(null); // from list
  const [suiteDetail, setSuiteDetail] = useState(null);       // full result JSON
  const [detailLoading, setDetailLoading] = useState(false);

  // ----- State: Detail table controls -----
  const [testFilter, setTestFilter] = useState("all"); // all | vuln | safe | skipped
  const [testSort, setTestSort] = useState("default");  // default | severity | protocol | target
  const [testSearch, setTestSearch] = useState("");

  // ----- State: Global refresh -----
  const [refreshing, setRefreshing] = useState(false);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------
  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const res = await fetch(`${apiUrl}/api/history/summary`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSummary(data.summary || data);
    } catch (err) {
      console.error("Failed to fetch summary:", err);
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, [apiUrl]);

  const fetchCharts = useCallback(async () => {
    setChartsLoading(true);
    try {
      const [protoRes, typeRes, deviceRes] = await Promise.allSettled([
        fetch(`${apiUrl}/api/history/vulns-by-protocol`),
        fetch(`${apiUrl}/api/history/vulns-by-type`),
        fetch(`${apiUrl}/api/history/vulns-by-device`),
      ]);
      if (protoRes.status === "fulfilled" && protoRes.value?.ok) setVulnsByProtocol((await protoRes.value.json()).data || []);
      if (typeRes.status === "fulfilled" && typeRes.value?.ok) setVulnsByType((await typeRes.value.json()).data || []);
      if (deviceRes.status === "fulfilled" && deviceRes.value?.ok) setVulnsByDevice((await deviceRes.value.json()).data || []);
    } catch (err) {
      console.error("Failed to fetch chart data:", err);
    } finally {
      setChartsLoading(false);
    }
  }, [apiUrl]);

  const fetchResults = useCallback(async () => {
    setResultsLoading(true);
    try {
      const res = await fetch(`${apiUrl}/api/results`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setResults(Array.isArray(data) ? data : data.results || []);
    } catch (err) {
      console.error("Failed to fetch results:", err);
      setResults([]);
    } finally {
      setResultsLoading(false);
    }
  }, [apiUrl]);

  const fetchSuiteDetail = useCallback(async (filename) => {
    setDetailLoading(true);
    setSuiteDetail(null);
    try {
      const res = await fetch(`${apiUrl}/api/results/${filename}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSuiteDetail(data);
    } catch (err) {
      console.error("Failed to fetch suite detail:", err);
    } finally {
      setDetailLoading(false);
    }
  }, [apiUrl]);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchSummary(), fetchCharts(), fetchResults()]);
    setRefreshing(false);
  }, [fetchSummary, fetchCharts, fetchResults]);

  const hasMountedRef = useRef(false);

  useEffect(() => {
    refreshAll().finally(() => { hasMountedRef.current = true; });
  }, [refreshAll]);

  // Auto-refresh when the tab becomes visible (after initial mount)
  useEffect(() => {
    if (visible && hasMountedRef.current) {
      refreshAll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // When a result is selected, fetch its full detail
  useEffect(() => {
    if (selectedResult?.file) {
      setTestFilter("all");
      setTestSort("default");
      setTestSearch("");
      fetchSuiteDetail(selectedResult.file);
    }
  }, [selectedResult, fetchSuiteDetail]);

  // -----------------------------------------------------------------------
  // Derived aggregate chart data
  // -----------------------------------------------------------------------
  const protocolChartData = useMemo(() =>
    (vulnsByProtocol || [])
      .map(d => ({ protocol: d.protocol || "unknown", vulns: d.vulns_found ?? d.vulns ?? 0 }))
      .sort((a, b) => b.vulns - a.vulns),
    [vulnsByProtocol]
  );

  const typeChartData = useMemo(() =>
    (vulnsByType || [])
      .map(d => ({ type: d.test_type || d.type || "unknown", vulns: d.vulns_found ?? d.vulns ?? 0 }))
      .sort((a, b) => b.vulns - a.vulns),
    [vulnsByType]
  );

  const deviceChartData = useMemo(() => {
    const byDevice = {};
    (vulnsByDevice || []).forEach(d => {
      const key = d.device || d.container_id || d.ip || "unknown";
      if (!byDevice[key]) byDevice[key] = { device: key, vulns: 0 };
      byDevice[key].vulns += d.vulns_found ?? d.vulns ?? 0;
    });
    return Object.values(byDevice).sort((a, b) => b.vulns - a.vulns);
  }, [vulnsByDevice]);

  const severityData = useMemo(() => {
    if (summary?.severity_breakdown) {
      return Object.entries(summary.severity_breakdown).map(([s, c]) => ({
        name: s.charAt(0).toUpperCase() + s.slice(1), value: c,
      }));
    }
    return [
      { name: "Critical", value: 0 }, { name: "High", value: 0 },
      { name: "Medium", value: 0 }, { name: "Low", value: 0 }, { name: "Info", value: 0 },
    ];
  }, [summary]);

  const hasSeverityData = severityData.some(d => d.value > 0);

  // -----------------------------------------------------------------------
  // Derived per-suite chart data (from full detail)
  // -----------------------------------------------------------------------
  const suiteCharts = useMemo(() => {
    if (!suiteDetail?.results) return null;
    const tests = suiteDetail.results;

    // Vulns by device
    const byDevice = {};
    tests.forEach(t => {
      const ip = t.target || "unknown";
      if (!byDevice[ip]) byDevice[ip] = { device: ip, vulns: 0, tests: 0 };
      byDevice[ip].tests++;
      if (t.vulnerability_found) byDevice[ip].vulns++;
    });
    const deviceData = Object.values(byDevice).sort((a, b) => b.vulns - a.vulns);

    // Vulns by protocol
    const byProto = {};
    tests.forEach(t => {
      const p = t.protocol || "unknown";
      if (!byProto[p]) byProto[p] = { protocol: p, vulns: 0, tests: 0 };
      byProto[p].tests++;
      if (t.vulnerability_found) byProto[p].vulns++;
    });
    const protoData = Object.values(byProto).sort((a, b) => b.vulns - a.vulns);

    // Severity breakdown (only vulns)
    const bySev = {};
    tests.forEach(t => {
      if (t.vulnerability_found) {
        const s = t.severity || "info";
        bySev[s] = (bySev[s] || 0) + 1;
      }
    });
    const sevData = Object.entries(bySev).map(([name, value]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1), value,
    }));

    // Vulns by type
    const byType = {};
    tests.forEach(t => {
      // Derive type from test_id
      const parts = (t.test_id || "").split("_");
      const type = parts.length > 1 ? parts.slice(1).join("_") : t.test_id || "unknown";
      if (!byType[type]) byType[type] = { type, vulns: 0 };
      if (t.vulnerability_found) byType[type].vulns++;
    });
    const typeData = Object.values(byType).filter(d => d.vulns > 0).sort((a, b) => b.vulns - a.vulns);

    return { deviceData, protoData, sevData, typeData, hasSev: sevData.length > 0 };
  }, [suiteDetail]);

  // Filtered & sorted tests for the detail table
  const filteredTests = useMemo(() => {
    if (!suiteDetail?.results) return [];
    let list = [...suiteDetail.results];

    // Search
    if (testSearch) {
      const q = testSearch.toLowerCase();
      list = list.filter(t =>
        (t.test_name || "").toLowerCase().includes(q) ||
        (t.test_id || "").toLowerCase().includes(q) ||
        (t.target || "").includes(q) ||
        (t.protocol || "").toLowerCase().includes(q)
      );
    }

    // Filter
    if (testFilter === "vuln") list = list.filter(t => t.vulnerability_found);
    else if (testFilter === "safe") list = list.filter(t => !t.vulnerability_found && t.status !== "skipped" && t.status !== "error");
    else if (testFilter === "skipped") list = list.filter(t => t.status === "skipped" || t.status === "error");
    else if (testFilter === "recommended") list = list.filter(t => t.is_recommended);

    // Sort
    const sevOrder = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    if (testSort === "severity") list.sort((a, b) => (sevOrder[a.severity] ?? 5) - (sevOrder[b.severity] ?? 5));
    else if (testSort === "protocol") list.sort((a, b) => (a.protocol || "").localeCompare(b.protocol || ""));
    else if (testSort === "target") list.sort((a, b) => (a.target || "").localeCompare(b.target || ""));
    else if (testSort === "result") list.sort((a, b) => (b.vulnerability_found ? 1 : 0) - (a.vulnerability_found ? 1 : 0));

    return list;
  }, [suiteDetail, testFilter, testSort, testSearch]);

  // =======================================================================
  // DETAIL VIEW — Per-Suite Results
  // =======================================================================
  if (selectedResult) {
    const row = selectedResult;
    const te = row.tests_executed ?? 0;
    const vd = row.vulns_detected ?? 0;
    const dr = te > 0 ? ((vd / te) * 100).toFixed(1) : "0";
    const skipped = suiteDetail?.results ? suiteDetail.results.filter(t => t.status === "skipped" || t.status === "error").length : 0;
    const recCount = suiteDetail?.results ? suiteDetail.results.filter(t => t.is_recommended).length : 0;

    return (
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Back button */}
        <button
          onClick={() => { setSelectedResult(null); setSuiteDetail(null); }}
          className="flex items-center gap-1 text-blue-600 hover:text-blue-800 text-sm font-medium transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Back to All Results
        </button>

        {/* ── Header Card ── */}
        <div className="bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 bg-gradient-to-r from-blue-600 to-indigo-600">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">
                  {row.suite_name || `Suite ${row.suite_id}`}
                </h2>
                <p className="text-blue-100 text-sm mt-0.5">
                  Suite ID: <span className="font-mono">{row.suite_id}</span>
                </p>
              </div>
              <div className="flex items-center gap-3">
                {statusBadge(row.status)}
                {row.execution_time_ms != null && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-white/20 text-white">
                    <Timer className="w-3 h-3" />
                    {formatDuration(row.execution_time_ms)}
                  </span>
                )}
              </div>
            </div>
            {row.finished_at && (
              <p className="text-blue-200 text-xs mt-2 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatDate(row.finished_at)}
              </p>
            )}
          </div>

          {/* ── Devices & Protocols Tested ── */}
          {row.devices && row.devices.length > 0 && (
            <div className="px-6 py-4 border-b border-gray-100">
              <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-3 flex items-center gap-1.5">
                <Server className="w-3.5 h-3.5" />
                Devices & Protocols Tested
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {row.devices.map((dev, i) => (
                  <div key={i} className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                    <span className="font-mono text-xs text-gray-700 font-semibold min-w-[100px]">
                      {dev.ip}
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {(dev.protocols || []).map(p => protocolBadge(p))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Suite KPIs ── */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 px-6 py-4">
            <div className="text-center">
              <FlaskConical className="w-6 h-6 mx-auto mb-1 text-blue-500" />
              <p className="text-xl font-bold">{te}</p>
              <p className="text-xs text-gray-600">Tests Executed</p>
            </div>
            <div className="text-center">
              <Bug className="w-6 h-6 mx-auto mb-1 text-red-500" />
              <p className="text-xl font-bold text-red-600">{vd}</p>
              <p className="text-xs text-gray-600">Vulnerabilities</p>
            </div>
            <div className="text-center">
              <ShieldAlert className="w-6 h-6 mx-auto mb-1 text-orange-500" />
              <p className="text-xl font-bold">{dr}%</p>
              <p className="text-xs text-gray-600">Detection Rate</p>
            </div>
            <div className="text-center">
              <Zap className="w-6 h-6 mx-auto mb-1 text-amber-500" />
              <p className="text-xl font-bold text-amber-600">{recCount}</p>
              <p className="text-xs text-gray-600">ML Recommended</p>
            </div>
            <div className="text-center">
              <AlertTriangle className="w-6 h-6 mx-auto mb-1 text-gray-600" />
              <p className="text-xl font-bold text-gray-600">{skipped}</p>
              <p className="text-xs text-gray-600">Skipped / Error</p>
            </div>
          </div>
        </div>

        {/* ── Per-Suite Charts ── */}
        {detailLoading ? (
          <div className="flex items-center justify-center py-16 text-gray-600">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            Loading suite details...
          </div>
        ) : suiteCharts && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Vulns by Device */}
            <Card>
              <CardHeader>Vulnerabilities by Device</CardHeader>
              <CardContent>
                {suiteCharts.deviceData.length === 0 ? (
                  <div className="flex items-center justify-center h-[250px] text-gray-600 text-sm">No data</div>
                ) : (
                  <ResponsiveContainer width="100%" height={Math.max(250, suiteCharts.deviceData.length * 40)}>
                    <BarChart data={suiteCharts.deviceData} layout="vertical" margin={{ left: 110 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis dataKey="device" type="category" width={105} tick={{ fontSize: 11 }} />
                      <Tooltip content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="bg-white shadow-lg rounded-lg p-3 text-sm border border-gray-200">
                            <p className="font-semibold text-gray-800">{d.device}</p>
                            <p className="text-red-600">Vulns: {d.vulns}</p>
                            <p className="text-gray-600">Tests: {d.tests}</p>
                          </div>
                        );
                      }} />
                      <Bar dataKey="vulns" name="Vulnerabilities" radius={[0, 4, 4, 0]}>
                        {suiteCharts.deviceData.map((_, i) => (
                          <Cell key={i} fill={BLUE_PALETTE[i % BLUE_PALETTE.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Vulns by Protocol */}
            <Card>
              <CardHeader>Vulnerabilities by Protocol</CardHeader>
              <CardContent>
                {suiteCharts.protoData.length === 0 ? (
                  <div className="flex items-center justify-center h-[250px] text-gray-600 text-sm">No data</div>
                ) : (
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={suiteCharts.protoData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="protocol" tick={{ fontSize: 12 }} />
                      <YAxis allowDecimals={false} />
                      <Tooltip content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="bg-white shadow-lg rounded-lg p-3 text-sm border border-gray-200">
                            <p className="font-semibold text-gray-800">{d.protocol}</p>
                            <p className="text-red-600">Vulns: {d.vulns}</p>
                            <p className="text-gray-600">Tests: {d.tests}</p>
                          </div>
                        );
                      }} />
                      <Bar dataKey="vulns" name="Vulnerabilities" radius={[4, 4, 0, 0]}>
                        {suiteCharts.protoData.map((entry, i) => (
                          <Cell key={i} fill={getProtocolColor(entry.protocol)} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Severity Distribution */}
            <Card>
              <CardHeader>Severity Distribution</CardHeader>
              <CardContent>
                {!suiteCharts.hasSev ? (
                  <div className="flex items-center justify-center h-[250px] text-gray-600 text-sm">
                    No vulnerabilities found
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie
                        data={suiteCharts.sevData}
                        cx="50%" cy="50%"
                        innerRadius={50} outerRadius={95}
                        paddingAngle={3} dataKey="value" nameKey="name"
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                        labelLine
                      >
                        {suiteCharts.sevData.map((entry, i) => (
                          <Cell key={i} fill={SEVERITY_COLORS[entry.name.toLowerCase()] || SEVERITY_PALETTE[i % SEVERITY_PALETTE.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value, name) => [value, name]} />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Vulns by Type */}
            <Card>
              <CardHeader>Vulnerability Types Found</CardHeader>
              <CardContent>
                {suiteCharts.typeData.length === 0 ? (
                  <div className="flex items-center justify-center h-[250px] text-gray-600 text-sm">
                    No vulnerabilities found
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={Math.max(250, suiteCharts.typeData.length * 30)}>
                    <BarChart data={suiteCharts.typeData.slice(0, 15)} layout="vertical" margin={{ left: 140 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis dataKey="type" type="category" width={135} tick={{ fontSize: 10 }} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="vulns" name="Vulnerabilities" radius={[0, 4, 4, 0]}>
                        {suiteCharts.typeData.slice(0, 15).map((_, i) => (
                          <Cell key={i} fill={BLUE_PALETTE[i % BLUE_PALETTE.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* ── Test Results Table ── */}
        {!detailLoading && suiteDetail?.results && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between w-full">
                <div className="flex items-center gap-2">
                  <Shield className="w-5 h-5 text-blue-500" />
                  <span>Individual Test Results</span>
                  <span className="text-xs text-gray-600 font-normal">({filteredTests.length} of {suiteDetail.results.length})</span>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* Controls */}
              <div className="flex flex-wrap gap-3 mb-4">
                {/* Search */}
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
                  <input
                    type="text"
                    value={testSearch}
                    onChange={e => setTestSearch(e.target.value)}
                    placeholder="Search tests..."
                    className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                  />
                </div>

                {/* Filter */}
                <div className="flex items-center gap-1">
                  <Filter className="w-4 h-4 text-gray-600" />
                  {[
                    { val: "all", label: "All" },
                    { val: "vuln", label: "Vulnerable" },
                    { val: "safe", label: "Safe" },
                    { val: "skipped", label: "Skipped" },
                    { val: "recommended", label: "Recommended" },
                  ].map(f => (
                    <button
                      key={f.val}
                      onClick={() => setTestFilter(f.val)}
                      className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                        testFilter === f.val
                          ? "bg-blue-600 text-white"
                          : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>

                {/* Sort */}
                <div className="flex items-center gap-1">
                  <ArrowUpDown className="w-4 h-4 text-gray-600" />
                  <select
                    value={testSort}
                    onChange={e => setTestSort(e.target.value)}
                    className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:ring-2 focus:ring-blue-500 outline-none"
                  >
                    <option value="default">Default</option>
                    <option value="severity">Severity</option>
                    <option value="protocol">Protocol</option>
                    <option value="target">Target IP</option>
                    <option value="result">Result</option>
                  </select>
                </div>
              </div>

              {/* Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left">
                      <th className="pb-3 pr-3 font-semibold text-gray-700">Test Name</th>
                      <th className="pb-3 pr-3 font-semibold text-gray-700">Target</th>
                      <th className="pb-3 pr-3 font-semibold text-gray-700 text-center">Port</th>
                      <th className="pb-3 pr-3 font-semibold text-gray-700">Protocol</th>
                      <th className="pb-3 pr-3 font-semibold text-gray-700">Severity</th>
                      <th className="pb-3 font-semibold text-gray-700 text-center">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTests.map((t, idx) => {
                      const isVuln = t.vulnerability_found;
                      const isSkipped = t.status === "skipped" || t.status === "error";
                      return (
                        <tr
                          key={`${t.test_id}-${t.target}-${idx}`}
                          className={`border-b border-gray-50 transition-colors ${
                            isVuln
                              ? "bg-red-50/60 hover:bg-red-50"
                              : isSkipped
                              ? "bg-gray-50/60 hover:bg-gray-50"
                              : "hover:bg-gray-50/50"
                          }`}
                        >
                          <td className="py-2.5 pr-3">
                            <div className="flex items-center gap-1.5">
                              <p className="font-medium text-gray-800 text-xs">{t.test_name}</p>
                              {t.is_recommended && (
                                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-amber-100 text-amber-700 whitespace-nowrap" title={`Risk score: ${t.risk_score ?? 'N/A'}`}>
                                  <Zap className="w-2.5 h-2.5" />
                                  Rec
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] text-gray-600 font-mono">{t.test_id}</p>
                          </td>
                          <td className="py-2.5 pr-3 font-mono text-xs text-gray-600">{t.target}</td>
                          <td className="py-2.5 pr-3 text-center font-mono text-xs text-gray-600">{t.port}</td>
                          <td className="py-2.5 pr-3">{protocolBadge(t.protocol)}</td>
                          <td className="py-2.5 pr-3">{severityBadge(t.severity)}</td>
                          <td className="py-2.5 text-center">
                            {isSkipped ? (
                              <span className="inline-flex items-center gap-1 text-xs text-gray-600">
                                <AlertTriangle className="w-3 h-3" />
                                {t.status}
                              </span>
                            ) : isVuln ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-700">
                                <Bug className="w-3 h-3" />
                                Vulnerable
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-700">
                                <CheckCircle2 className="w-3 h-3" />
                                Safe
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {filteredTests.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-gray-600 text-sm">
                          No tests match the current filter.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    );
  }

  // =======================================================================
  // AGGREGATE VIEW — All Results Overview
  // =======================================================================
  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Test Results</h2>
        <button
          onClick={refreshAll}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {KPI_DEFS.map(({ key, label, icon: Icon, color, format }) => (
          <Card key={key}>
            <CardContent className="flex flex-col items-center py-4">
              <Icon className={`w-8 h-8 mb-2 ${color}`} />
              {summaryLoading ? (
                <Loader2 className="w-6 h-6 animate-spin text-gray-600 mb-1" />
              ) : (
                <span className="text-2xl font-bold">
                  {summary ? format(summary[key]) : "--"}
                </span>
              )}
              <span className="text-xs text-gray-600 mt-1 text-center">{label}</span>
              {/* Show total raw executions as context under Unique Tests */}
              {key === "total_tests" && summary?.total_runs != null && !summaryLoading && (
                <span className="text-[10px] text-gray-600 mt-0.5">
                  ({summary.total_runs.toLocaleString()} total executions)
                </span>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ── Aggregate Charts ── */}
      {chartsLoading ? (
        <div className="flex items-center justify-center py-16 text-gray-600">
          <Loader2 className="w-6 h-6 animate-spin mr-2" />
          Loading charts...
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Vulns by Protocol */}
          <Card>
            <CardHeader>Vulns by Protocol</CardHeader>
            <CardContent>
              {protocolChartData.length === 0 ? (
                <div className="flex items-center justify-center h-[300px] text-gray-600 text-sm">No data available</div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={protocolChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="protocol" tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} />
                    <Tooltip content={<ChartTooltip />} />
                    <Bar dataKey="vulns" name="Vulnerabilities" radius={[4, 4, 0, 0]}>
                      {protocolChartData.map((entry, i) => (
                        <Cell key={i} fill={getProtocolColor(entry.protocol)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Vulns by Type */}
          <Card>
            <CardHeader>Vulns by Type</CardHeader>
            <CardContent>
              {typeChartData.length === 0 ? (
                <div className="flex items-center justify-center h-[300px] text-gray-600 text-sm">No data available</div>
              ) : (
                <ResponsiveContainer width="100%" height={Math.max(300, typeChartData.length * 35)}>
                  <BarChart data={typeChartData} layout="vertical" margin={{ left: 120 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis dataKey="type" type="category" width={110} tick={{ fontSize: 12 }} />
                    <Tooltip content={<ChartTooltip />} />
                    <Bar dataKey="vulns" name="Vulnerabilities" radius={[0, 4, 4, 0]}>
                      {typeChartData.map((_, i) => (
                        <Cell key={i} fill={BLUE_PALETTE[i % BLUE_PALETTE.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Vulns by Device */}
          <Card>
            <CardHeader>Vulns by Device</CardHeader>
            <CardContent>
              {deviceChartData.length === 0 ? (
                <div className="flex items-center justify-center h-[300px] text-gray-600 text-sm">No data available</div>
              ) : (
                <ResponsiveContainer width="100%" height={Math.max(300, deviceChartData.length * 40)}>
                  <BarChart data={deviceChartData} layout="vertical" margin={{ left: 120 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis dataKey="device" type="category" width={110} tick={{ fontSize: 11 }} />
                    <Tooltip content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0].payload;
                      return (
                        <div className="bg-white shadow-lg rounded-lg p-3 text-sm border border-gray-200">
                          <p className="font-semibold text-gray-800">{d.device}</p>
                          <p>Vulnerabilities: {d.vulns}</p>
                        </div>
                      );
                    }} />
                    <Bar dataKey="vulns" name="Vulnerabilities" radius={[0, 4, 4, 0]}>
                      {deviceChartData.map((_, i) => (
                        <Cell key={i} fill={BLUE_PALETTE[i % BLUE_PALETTE.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          {/* Severity Distribution */}
          <Card>
            <CardHeader>Severity Distribution</CardHeader>
            <CardContent>
              {!hasSeverityData ? (
                <div className="flex flex-col items-center justify-center h-[300px] text-gray-600 text-sm">
                  <ShieldAlert className="w-10 h-10 mb-2 text-gray-600" />
                  <p>No severity data available</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={severityData} cx="50%" cy="50%"
                      innerRadius={60} outerRadius={110} paddingAngle={3}
                      dataKey="value" nameKey="name"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                      labelLine
                    >
                      {severityData.map((entry, i) => (
                        <Cell key={i} fill={SEVERITY_COLORS[entry.name.toLowerCase()] || SEVERITY_PALETTE[i % SEVERITY_PALETTE.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value, name) => [value, name]} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Suite Runs Table ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-blue-500" />
            Suite Runs
          </div>
        </CardHeader>
        <CardContent>
          {resultsLoading ? (
            <div className="flex items-center justify-center py-12 text-gray-600">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Loading results...
            </div>
          ) : results.length === 0 ? (
            <div className="text-center py-12 text-gray-600 text-sm">
              No past results found. Run a test suite to see results here.
            </div>
          ) : (
            <div className="space-y-3">
              {results.map((row, idx) => {
                const suiteId = row.suite_id || `#${idx + 1}`;
                const te = row.tests_executed ?? 0;
                const vd = row.vulns_detected ?? 0;
                const dr = row.detection_rate != null ? (Number(row.detection_rate) * 100).toFixed(1) : (te > 0 ? ((vd / te) * 100).toFixed(1) : "0");

                return (
                  <div
                    key={`${suiteId}-${idx}`}
                    onClick={() => setSelectedResult(row)}
                    className="bg-white border border-gray-200 rounded-xl p-4 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer group"
                  >
                    {/* Top row: name, status, date */}
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <h4 className="font-semibold text-gray-800 text-sm group-hover:text-blue-700 transition-colors">
                          {row.suite_name || `Suite ${suiteId}`}
                        </h4>
                        {statusBadge(row.status)}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-gray-600">
                        {row.execution_time_ms != null && (
                          <span className="flex items-center gap-1">
                            <Timer className="w-3 h-3" />
                            {formatDuration(row.execution_time_ms)}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatDate(row.finished_at)}
                        </span>
                      </div>
                    </div>

                    {/* Middle row: devices + protocols */}
                    {row.devices && row.devices.length > 0 && (
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <span className="text-xs text-gray-600 flex items-center gap-1">
                          <Server className="w-3 h-3" />
                          {row.devices.length} device{row.devices.length !== 1 ? "s" : ""}
                        </span>
                        <span className="text-gray-600">|</span>
                        <div className="flex flex-wrap gap-1">
                          {(row.protocols || []).map(p => protocolBadge(p))}
                        </div>
                      </div>
                    )}

                    {/* Bottom row: stats */}
                    <div className="flex items-center gap-4 text-xs">
                      <span className="text-gray-600">
                        <span className="font-semibold">{te}</span> tests
                      </span>
                      <span className="text-red-600">
                        <span className="font-bold">{vd}</span> vulns
                      </span>
                      <span className={`font-semibold ${
                        Number(dr) >= 50 ? "text-red-600" : Number(dr) >= 25 ? "text-orange-600" : "text-green-600"
                      }`}>
                        {dr}% detection
                      </span>

                      {/* Severity mini-badges from the list-level data */}
                      {row.severity_breakdown && Object.keys(row.severity_breakdown).length > 0 && (
                        <div className="flex items-center gap-1 ml-auto">
                          {["critical", "high", "medium", "low"].map(sev => {
                            const count = row.severity_breakdown[sev];
                            if (!count) return null;
                            return (
                              <span
                                key={sev}
                                className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${SEVERITY_BG[sev]}`}
                                title={`${sev}: ${count}`}
                              >
                                {count} {sev.charAt(0).toUpperCase()}
                              </span>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
