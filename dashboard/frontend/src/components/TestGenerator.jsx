import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  Search,
  Plus,
  Loader2,
  CheckCircle2,
  XCircle,
  Wifi,
  Monitor,
  Server,
  Globe,
  Radio,
  Terminal,
  Lock,
  FolderOpen,
  Eye,
  Cpu,
  Satellite,
  Network,
  Shield,
  Zap,
  Settings,
  ChevronDown,
  ChevronUp,
  Sparkles,
  FileText,
  ToggleLeft,
  ToggleRight,
  RefreshCw,
  Trash2,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Protocol definitions with icons and display metadata
// ---------------------------------------------------------------------------
const PROTOCOLS = [
  { id: "http", name: "HTTP", icon: Globe, color: "blue" },
  { id: "mqtt", name: "MQTT", icon: Radio, color: "green" },
  { id: "ssh", name: "SSH", icon: Lock, color: "gray" },
  { id: "ftp", name: "FTP", icon: FolderOpen, color: "yellow" },
  { id: "telnet", name: "Telnet", icon: Terminal, color: "red" },
  { id: "coap", name: "CoAP", icon: Satellite, color: "indigo" },
  { id: "modbus", name: "Modbus", icon: Cpu, color: "orange" },
  { id: "dns", name: "DNS", icon: Network, color: "purple" },
  { id: "rtsp", name: "RTSP", icon: Eye, color: "pink" },
];

// Port-to-protocol mapping for discovered protocol inference
const PORT_TO_PROTOCOL = {
  21: "ftp", 22: "ssh", 23: "telnet", 53: "dns", 80: "http",
  443: "http", 502: "modbus", 554: "rtsp", 1883: "mqtt",
  5683: "coap", 8080: "http", 8883: "mqtt",
};

// Color mappings for protocol card styling
const PROTOCOL_COLORS = {
  blue: {
    bg: "bg-blue-50",
    border: "border-blue-200",
    activeBg: "bg-blue-100",
    activeBorder: "border-blue-500",
    text: "text-blue-700",
    icon: "text-blue-500",
    badge: "bg-blue-100 text-blue-700",
  },
  green: {
    bg: "bg-green-50",
    border: "border-green-200",
    activeBg: "bg-green-100",
    activeBorder: "border-green-500",
    text: "text-green-700",
    icon: "text-green-500",
    badge: "bg-green-100 text-green-700",
  },
  gray: {
    bg: "bg-gray-50",
    border: "border-gray-200",
    activeBg: "bg-gray-100",
    activeBorder: "border-gray-500",
    text: "text-gray-700",
    icon: "text-gray-500",
    badge: "bg-gray-100 text-gray-700",
  },
  yellow: {
    bg: "bg-yellow-50",
    border: "border-yellow-200",
    activeBg: "bg-yellow-100",
    activeBorder: "border-yellow-500",
    text: "text-yellow-700",
    icon: "text-yellow-500",
    badge: "bg-yellow-100 text-yellow-700",
  },
  red: {
    bg: "bg-red-50",
    border: "border-red-200",
    activeBg: "bg-red-100",
    activeBorder: "border-red-500",
    text: "text-red-700",
    icon: "text-red-500",
    badge: "bg-red-100 text-red-700",
  },
  indigo: {
    bg: "bg-indigo-50",
    border: "border-indigo-200",
    activeBg: "bg-indigo-100",
    activeBorder: "border-indigo-500",
    text: "text-indigo-700",
    icon: "text-indigo-500",
    badge: "bg-indigo-100 text-indigo-700",
  },
  orange: {
    bg: "bg-orange-50",
    border: "border-orange-200",
    activeBg: "bg-orange-100",
    activeBorder: "border-orange-500",
    text: "text-orange-700",
    icon: "text-orange-500",
    badge: "bg-orange-100 text-orange-700",
  },
  purple: {
    bg: "bg-purple-50",
    border: "border-purple-200",
    activeBg: "bg-purple-100",
    activeBorder: "border-purple-500",
    text: "text-purple-700",
    icon: "text-purple-500",
    badge: "bg-purple-100 text-purple-700",
  },
  pink: {
    bg: "bg-pink-50",
    border: "border-pink-200",
    activeBg: "bg-pink-100",
    activeBorder: "border-pink-500",
    text: "text-pink-700",
    icon: "text-pink-500",
    badge: "bg-pink-100 text-pink-700",
  },
  teal: {
    bg: "bg-teal-50",
    border: "border-teal-200",
    activeBg: "bg-teal-100",
    activeBorder: "border-teal-500",
    text: "text-teal-700",
    icon: "text-teal-500",
    badge: "bg-teal-100 text-teal-700",
  },
};

// Severity level definitions
const SEVERITY_LEVELS = [
  { id: "critical", label: "Critical", color: "bg-red-500" },
  { id: "high", label: "High", color: "bg-orange-500" },
  { id: "medium", label: "Medium", color: "bg-yellow-500" },
  { id: "low", label: "Low", color: "bg-blue-500" },
  { id: "info", label: "Info", color: "bg-gray-400" },
];

// ---------------------------------------------------------------------------
// Protocol icon helper for device cards
// ---------------------------------------------------------------------------
function getProtocolIcon(protocolName) {
  const lower = protocolName.toLowerCase();
  const match = PROTOCOLS.find((p) => lower.includes(p.id));
  if (match) {
    const Icon = match.icon;
    const colors = PROTOCOL_COLORS[match.color];
    return { Icon, colors, name: match.name };
  }
  return { Icon: Server, colors: PROTOCOL_COLORS.gray, name: protocolName };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function TestGenerator({ apiUrl, onSuiteGenerated }) {
  // ---- Scan Network State ----
  const [cidr, setCidr] = useState("172.20.0.0/27");
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState(null);
  const scanPollRef = useRef(null);

  // ---- Manual Add State ----
  const [manualIp, setManualIp] = useState("");
  const [manualPorts, setManualPorts] = useState("");
  const [addingDevice, setAddingDevice] = useState(false);
  const [addError, setAddError] = useState(null);

  // ---- Devices State ----
  const [devices, setDevices] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [selectedDeviceIds, setSelectedDeviceIds] = useState(new Set());

  // ---- Protocol State ----
  const [protocolCounts, setProtocolCounts] = useState({});
  const [selectedProtocols, setSelectedProtocols] = useState(new Set());
  const [loadingProtocols, setLoadingProtocols] = useState(false);

  // ---- Generation Options State ----
  const [includeUncommon, setIncludeUncommon] = useState(true);
  const [severityFilter, setSeverityFilter] = useState({
    critical: true,
    high: true,
    medium: true,
    low: true,
    info: true,
  });
  const [suiteName, setSuiteName] = useState("");
  const [forceNew, setForceNew] = useState(false);

  // ---- AutoML Framework State ----
  const [automlTool, setAutomlTool] = useState("h2o");
  const [availableFrameworks, setAvailableFrameworks] = useState(["h2o"]);

  // ---- Generation State ----
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [generateSuccess, setGenerateSuccess] = useState(null);

  // =========================================================================
  // Fetch Devices
  // =========================================================================
  const fetchDevices = useCallback(async () => {
    setLoadingDevices(true);
    try {
      const res = await fetch(`${apiUrl}/api/devices`);
      if (!res.ok) throw new Error(`Failed to fetch devices: ${res.status}`);
      const data = await res.json();
      const deviceList = Array.isArray(data) ? data : data.devices || [];
      setDevices(deviceList);
    } catch (err) {
      console.error("Error fetching devices:", err);
    } finally {
      setLoadingDevices(false);
    }
  }, [apiUrl]);

  // =========================================================================
  // Fetch Protocol Counts
  // =========================================================================
  const fetchProtocols = useCallback(async () => {
    setLoadingProtocols(true);
    try {
      const res = await fetch(`${apiUrl}/api/protocols`);
      if (!res.ok) throw new Error(`Failed to fetch protocols: ${res.status}`);
      const data = await res.json();
      setProtocolCounts(data);
    } catch (err) {
      console.error("Error fetching protocols:", err);
    } finally {
      setLoadingProtocols(false);
    }
  }, [apiUrl]);

  // =========================================================================
  // Compute discovered protocols from scanned devices
  // =========================================================================
  const discoveredProtocols = useMemo(() => {
    const protoDeviceCount = {};
    devices.forEach((device) => {
      const deviceProtos = new Set();

      // From device.protocols field
      (device.protocols || []).forEach((p) => {
        const lower = typeof p === "string" ? p.toLowerCase() : "";
        if (lower) deviceProtos.add(lower);
      });

      // Infer from ports
      (device.ports || []).forEach((port) => {
        const portNum = typeof port === "object" ? port.port || port.number : parseInt(port, 10);
        const proto = PORT_TO_PROTOCOL[portNum];
        if (proto) deviceProtos.add(proto);
      });

      deviceProtos.forEach((proto) => {
        protoDeviceCount[proto] = (protoDeviceCount[proto] || 0) + 1;
      });
    });
    return protoDeviceCount;
  }, [devices]);

  // =========================================================================
  // Load devices and protocols on mount
  // =========================================================================
  useEffect(() => {
    fetchDevices();
    fetchProtocols();
    // Fetch available AutoML frameworks
    fetch(`${apiUrl}/api/automl/frameworks`)
      .then((r) => r.json())
      .then((d) => {
        const fws = (d.frameworks || []).map((f) => f.name);
        if (fws.length > 0) setAvailableFrameworks(fws);
      })
      .catch(() => {});
  }, [fetchDevices, fetchProtocols]);

  // =========================================================================
  // Auto-select protocols based on selected devices
  // =========================================================================
  useEffect(() => {
    if (selectedDeviceIds.size === 0) return;

    const deviceProtocols = new Set();
    devices
      .filter((d) => selectedDeviceIds.has(d.id ?? d.ip))
      .forEach((device) => {
        const protos = device.protocols || [];
        protos.forEach((p) => {
          const lower = typeof p === "string" ? p.toLowerCase() : "";
          PROTOCOLS.forEach((proto) => {
            if (lower.includes(proto.id)) {
              deviceProtocols.add(proto.id);
            }
          });
        });

        // Also infer protocols from ports
        const ports = device.ports || [];
        ports.forEach((port) => {
          const portNum = typeof port === "object" ? port.port || port.number : parseInt(port, 10);
          if (portNum === 80 || portNum === 443 || portNum === 8080) deviceProtocols.add("http");
          if (portNum === 1883 || portNum === 8883) deviceProtocols.add("mqtt");
          if (portNum === 22) deviceProtocols.add("ssh");
          if (portNum === 21) deviceProtocols.add("ftp");
          if (portNum === 23) deviceProtocols.add("telnet");
          if (portNum === 5683) deviceProtocols.add("coap");
          if (portNum === 502) deviceProtocols.add("modbus");
          if (portNum === 53) deviceProtocols.add("dns");
          if (portNum === 554) deviceProtocols.add("rtsp");
        });
      });

    if (deviceProtocols.size > 0) {
      setSelectedProtocols(deviceProtocols);
    }
  }, [selectedDeviceIds, devices]);

  // =========================================================================
  // Cleanup scan polling on unmount
  // =========================================================================
  useEffect(() => {
    return () => {
      if (scanPollRef.current) {
        clearInterval(scanPollRef.current);
      }
    };
  }, []);

  // =========================================================================
  // Scan Network
  // =========================================================================
  const handleScan = useCallback(async () => {
    setScanning(true);
    setScanError(null);

    try {
      const res = await fetch(`${apiUrl}/api/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ network: cidr }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.message || `Scan request failed: ${res.status}`);
      }

      // Start polling for scan status
      scanPollRef.current = setInterval(async () => {
        try {
          const statusRes = await fetch(`${apiUrl}/api/scan/status`);
          if (!statusRes.ok) return;

          const statusData = await statusRes.json();

          if (statusData.status === "completed") {
            clearInterval(scanPollRef.current);
            scanPollRef.current = null;
            setScanning(false);
            // Refresh devices list after scan completes
            await fetchDevices();
            await fetchProtocols();
          } else if (statusData.status === "error" || statusData.status === "failed") {
            clearInterval(scanPollRef.current);
            scanPollRef.current = null;
            setScanning(false);
            setScanError(statusData.message || "Scan failed");
          }
        } catch (pollErr) {
          // Ignore transient poll errors
        }
      }, 2000);
    } catch (err) {
      setScanning(false);
      setScanError(err.message);
    }
  }, [apiUrl, cidr, fetchDevices, fetchProtocols]);

  // =========================================================================
  // Add Device Manually
  // =========================================================================
  const handleAddDevice = useCallback(async () => {
    if (!manualIp.trim()) return;
    setAddingDevice(true);
    setAddError(null);

    try {
      const ports = manualPorts
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean)
        .map((p) => parseInt(p, 10))
        .filter((p) => !isNaN(p));

      const res = await fetch(`${apiUrl}/api/devices`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip: manualIp.trim(), ports }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.message || `Failed to add device: ${res.status}`);
      }

      setManualIp("");
      setManualPorts("");
      await fetchDevices();
      await fetchProtocols();
    } catch (err) {
      setAddError(err.message);
    } finally {
      setAddingDevice(false);
    }
  }, [apiUrl, manualIp, manualPorts, fetchDevices, fetchProtocols]);

  // =========================================================================
  // Toggle device selection
  // =========================================================================
  const toggleDevice = useCallback((deviceId) => {
    setSelectedDeviceIds((prev) => {
      const next = new Set(prev);
      if (next.has(deviceId)) {
        next.delete(deviceId);
      } else {
        next.add(deviceId);
      }
      return next;
    });
  }, []);

  // =========================================================================
  // Select / Deselect all devices
  // =========================================================================
  const selectAllDevices = useCallback(() => {
    const allIds = new Set(devices.map((d) => d.id ?? d.ip));
    setSelectedDeviceIds(allIds);
  }, [devices]);

  const deselectAllDevices = useCallback(() => {
    setSelectedDeviceIds(new Set());
  }, []);

  // =========================================================================
  // Toggle protocol selection
  // =========================================================================
  const toggleProtocol = useCallback((protocolId) => {
    setSelectedProtocols((prev) => {
      const next = new Set(prev);
      if (next.has(protocolId)) {
        next.delete(protocolId);
      } else {
        next.add(protocolId);
      }
      return next;
    });
  }, []);

  // =========================================================================
  // Toggle severity filter
  // =========================================================================
  const toggleSeverity = useCallback((severityId) => {
    setSeverityFilter((prev) => ({
      ...prev,
      [severityId]: !prev[severityId],
    }));
  }, []);

  // =========================================================================
  // Generate Test Suite
  // =========================================================================
  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setGenerateError(null);
    setGenerateSuccess(null);

    try {
      const selectedDevices = devices
        .filter((d) => selectedDeviceIds.has(d.id ?? d.ip))
        .map((d) => ({ ip: d.ip, ports: d.ports || [] }));

      const activeSeverities = Object.entries(severityFilter)
        .filter(([, enabled]) => enabled)
        .map(([id]) => id);

      const payload = {
        devices: selectedDevices,
        protocols: Array.from(selectedProtocols),
        include_uncommon: includeUncommon,
        severity_filter: activeSeverities,
        name: suiteName.trim() || undefined,
        force_new: forceNew,
        automl_tool: automlTool,
      };

      const res = await fetch(`${apiUrl}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.message || `Generation failed: ${res.status}`);
      }

      const data = await res.json();
      setGenerateSuccess({
        testCount: data.test_count ?? data.total_tests ?? 0,
        recommendedCount: data.recommended_count ?? 0,
        suiteName: data.suite_name ?? data.name ?? suiteName,
        suiteId: data.suite_id ?? data.id ?? null,
        action: data.action ?? "created",
        testsAdded: data.tests_added ?? 0,
        enhancementCount: data.metadata?.enhancement_count ?? 0,
      });

      if (onSuiteGenerated) {
        onSuiteGenerated(data);
      }
    } catch (err) {
      setGenerateError(err.message);
    } finally {
      setGenerating(false);
    }
  }, [
    apiUrl,
    devices,
    selectedDeviceIds,
    selectedProtocols,
    includeUncommon,
    severityFilter,
    suiteName,
    forceNew,
    automlTool,
    onSuiteGenerated,
  ]);

  // =========================================================================
  // Helpers
  // =========================================================================
  const getDeviceId = (device) => device.id ?? device.ip;
  const isDeviceScanned = (device) => device.source === "scanned" || device.scanned === true;
  const allDevicesSelected =
    devices.length > 0 && selectedDeviceIds.size === devices.length;

  const canGenerate =
    selectedDeviceIds.size > 0 &&
    selectedProtocols.size > 0 &&
    Object.values(severityFilter).some(Boolean);

  // =========================================================================
  // Render: Device card
  // =========================================================================
  const renderDeviceCard = (device) => {
    const id = getDeviceId(device);
    const isSelected = selectedDeviceIds.has(id);
    const scanned = isDeviceScanned(device);
    const ports = device.ports || [];
    const protocols = device.protocols || [];

    return (
      <div
        key={id}
        onClick={() => toggleDevice(id)}
        className={`relative rounded-xl border-2 p-4 cursor-pointer transition-all duration-200 hover:shadow-md ${
          isSelected
            ? scanned
              ? "border-blue-500 bg-blue-50/50 shadow-sm shadow-blue-100"
              : "border-green-500 bg-green-50/50 shadow-sm shadow-green-100"
            : scanned
            ? "border-blue-200 bg-white hover:border-blue-300"
            : "border-green-200 bg-white hover:border-green-300"
        }`}
      >
        {/* Selection checkbox */}
        <div className="absolute top-3 right-3">
          <div
            className={`w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
              isSelected
                ? scanned
                  ? "bg-blue-500 border-blue-500"
                  : "bg-green-500 border-green-500"
                : "border-gray-300 bg-white"
            }`}
          >
            {isSelected && (
              <CheckCircle2 className="w-3.5 h-3.5 text-white" />
            )}
          </div>
        </div>

        {/* Device IP */}
        <div className="flex items-center gap-2 mb-2">
          <Monitor
            className={`w-4 h-4 flex-shrink-0 ${
              scanned ? "text-blue-500" : "text-green-500"
            }`}
          />
          <span className="font-mono text-sm font-semibold text-gray-800">
            {device.ip}
          </span>
        </div>

        {/* Source badge */}
        <span
          className={`inline-block text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full mb-2 ${
            scanned
              ? "bg-blue-100 text-blue-600"
              : "bg-green-100 text-green-600"
          }`}
        >
          {scanned ? "Scanned" : "Manual"}
        </span>

        {/* Ports as badges */}
        {ports.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {ports.map((port, idx) => {
              const portNum =
                typeof port === "object"
                  ? port.port || port.number
                  : port;
              return (
                <span
                  key={idx}
                  className="inline-block text-xs font-mono bg-gray-100 text-gray-600 px-2 py-0.5 rounded-md border border-gray-200"
                >
                  {portNum}
                </span>
              );
            })}
          </div>
        )}

        {/* Protocol icons */}
        {protocols.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {protocols.map((proto, idx) => {
              const protoName =
                typeof proto === "string" ? proto : proto.name || "";
              const { Icon, colors, name } = getProtocolIcon(protoName);
              return (
                <span
                  key={idx}
                  className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-md ${colors.badge}`}
                  title={name}
                >
                  <Icon className="w-3 h-3" />
                  {name}
                </span>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  // =========================================================================
  // RENDER
  // =========================================================================
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* ================================================================= */}
      {/* LEFT PANEL — Device Input                                         */}
      {/* ================================================================= */}
      <div className="space-y-5">
        {/* ---- Scan Network Section ---- */}
        <div className="bg-white shadow-md rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 bg-gradient-to-r from-blue-600 to-indigo-600 flex items-center gap-2.5">
            <Wifi className="w-5 h-5 text-white" />
            <h3 className="text-white font-bold text-sm">Scan Network</h3>
          </div>
          <div className="p-5 space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                CIDR Range
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={cidr}
                  onChange={(e) => setCidr(e.target.value)}
                  placeholder="172.20.0.0/27"
                  disabled={scanning}
                  className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400"
                />
                <button
                  onClick={handleScan}
                  disabled={scanning || !cidr.trim()}
                  className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-semibold flex items-center gap-2 transition-all shadow-sm shadow-blue-200 hover:shadow-blue-300"
                >
                  {scanning ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Scanning...
                    </>
                  ) : (
                    <>
                      <Search className="w-4 h-4" />
                      Scan
                    </>
                  )}
                </button>
              </div>
            </div>

            {scanning && (
              <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-xl px-4 py-3">
                <Loader2 className="w-4 h-4 text-blue-500 animate-spin flex-shrink-0" />
                <p className="text-xs text-blue-700">
                  Scanning network <span className="font-mono font-semibold">{cidr}</span>... This may take a moment.
                </p>
              </div>
            )}

            {scanError && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
                <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                <p className="text-xs text-red-700">{scanError}</p>
              </div>
            )}
          </div>
        </div>

        {/* ---- Add Manually Section ---- */}
        <div className="bg-white shadow-md rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 bg-gradient-to-r from-green-600 to-emerald-600 flex items-center gap-2.5">
            <Plus className="w-5 h-5 text-white" />
            <h3 className="text-white font-bold text-sm">Add Manually</h3>
          </div>
          <div className="p-5 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1.5">
                  IP Address
                </label>
                <input
                  type="text"
                  value={manualIp}
                  onChange={(e) => setManualIp(e.target.value)}
                  placeholder="192.168.1.100"
                  disabled={addingDevice}
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-green-400 focus:border-transparent disabled:bg-gray-50"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1.5">
                  Ports (comma-separated)
                </label>
                <input
                  type="text"
                  value={manualPorts}
                  onChange={(e) => setManualPorts(e.target.value)}
                  placeholder="80, 443, 22, 1883"
                  disabled={addingDevice}
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-green-400 focus:border-transparent disabled:bg-gray-50"
                />
              </div>
            </div>
            <button
              onClick={handleAddDevice}
              disabled={addingDevice || !manualIp.trim()}
              className="w-full py-2.5 rounded-xl bg-green-600 hover:bg-green-700 disabled:bg-green-300 text-white text-sm font-semibold flex items-center justify-center gap-2 transition-all shadow-sm shadow-green-200 hover:shadow-green-300"
            >
              {addingDevice ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <Plus className="w-4 h-4" />
                  Add Device
                </>
              )}
            </button>

            {addError && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
                <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                <p className="text-xs text-red-700">{addError}</p>
              </div>
            )}
          </div>
        </div>

        {/* ---- Device List Section ---- */}
        <div className="bg-white shadow-md rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Server className="w-5 h-5 text-gray-600" />
              <h3 className="font-bold text-sm text-gray-800">
                Devices
                {devices.length > 0 && (
                  <span className="ml-2 text-xs font-normal text-gray-400">
                    ({selectedDeviceIds.size}/{devices.length} selected)
                  </span>
                )}
              </h3>
            </div>
            <div className="flex items-center gap-2">
              {devices.length > 0 && (
                <>
                  <button
                    onClick={allDevicesSelected ? deselectAllDevices : selectAllDevices}
                    className="text-xs text-blue-600 hover:text-blue-700 font-medium transition"
                  >
                    {allDevicesSelected ? "Deselect All" : "Select All"}
                  </button>
                  <span className="text-gray-300">|</span>
                </>
              )}
              <button
                onClick={() => {
                  fetchDevices();
                  fetchProtocols();
                }}
                disabled={loadingDevices}
                className="text-xs text-gray-500 hover:text-gray-700 font-medium flex items-center gap-1 transition"
              >
                <RefreshCw
                  className={`w-3 h-3 ${loadingDevices ? "animate-spin" : ""}`}
                />
                Refresh
              </button>
            </div>
          </div>

          <div className="p-5">
            {loadingDevices ? (
              <div className="flex items-center justify-center py-8 gap-2 text-gray-400">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span className="text-sm">Loading devices...</span>
              </div>
            ) : devices.length === 0 ? (
              <div className="text-center py-8">
                <Monitor className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                <p className="text-sm text-gray-400">No devices found</p>
                <p className="text-xs text-gray-300 mt-1">
                  Scan the network or add devices manually
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[480px] overflow-y-auto pr-1">
                {devices.map((device) => renderDeviceCard(device))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ================================================================= */}
      {/* RIGHT PANEL — Protocol & Generation                               */}
      {/* ================================================================= */}
      <div className="space-y-5">
        {/* ---- Protocol Grid Section ---- */}
        <div className="bg-white shadow-md rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-200 flex items-center gap-2.5">
            <Shield className="w-5 h-5 text-gray-600" />
            <h3 className="font-bold text-sm text-gray-800">
              Protocols
              {selectedProtocols.size > 0 && (
                <span className="ml-2 text-xs font-normal text-gray-400">
                  ({selectedProtocols.size} selected)
                </span>
              )}
            </h3>
          </div>
          <div className="p-5">
            {loadingProtocols ? (
              <div className="flex items-center justify-center py-8 gap-2 text-gray-400">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span className="text-sm">Loading protocols...</span>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {PROTOCOLS.map((protocol) => {
                  const ProtoIcon = protocol.icon;
                  const colors = PROTOCOL_COLORS[protocol.color];
                  const isSelected = selectedProtocols.has(protocol.id);
                  const deviceCount = discoveredProtocols[protocol.id] || 0;
                  const isDiscovered = deviceCount > 0;
                  const testCount =
                    protocolCounts[protocol.id] ??
                    protocolCounts[protocol.name] ??
                    protocolCounts[protocol.name.toLowerCase()] ??
                    0;

                  return (
                    <div
                      key={protocol.id}
                      onClick={() => toggleProtocol(protocol.id)}
                      className={`relative rounded-xl border-2 p-3.5 cursor-pointer transition-all duration-200 hover:shadow-md ${
                        isSelected
                          ? `${colors.activeBg} ${colors.activeBorder} shadow-sm`
                          : isDiscovered
                          ? `${colors.bg} ${colors.border} hover:opacity-80`
                          : "bg-gray-50 border-gray-200 opacity-50 hover:opacity-70"
                      }`}
                    >
                      {/* Toggle checkbox */}
                      <div className="absolute top-2.5 right-2.5">
                        <div
                          className={`w-4 h-4 rounded-md border-2 flex items-center justify-center transition-all ${
                            isSelected
                              ? `${colors.activeBorder.replace("border", "bg")} ${colors.activeBorder}`
                              : "border-gray-300 bg-white"
                          }`}
                        >
                          {isSelected && (
                            <CheckCircle2 className="w-3 h-3 text-white" />
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 mb-1.5">
                        <ProtoIcon className={`w-5 h-5 ${isDiscovered || isSelected ? colors.icon : "text-gray-400"}`} />
                        <span className={`text-sm font-bold ${isDiscovered || isSelected ? colors.text : "text-gray-400"}`}>
                          {protocol.name}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <p className="text-xs text-gray-500">
                          {testCount} {testCount === 1 ? "test" : "tests"}
                        </p>
                        {devices.length > 0 && (
                          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                            isDiscovered
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-gray-100 text-gray-400"
                          }`}>
                            {isDiscovered ? `${deviceCount} ${deviceCount === 1 ? "device" : "devices"}` : "Not found"}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* ---- Generation Options Section ---- */}
        <div className="bg-white shadow-md rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-200 flex items-center gap-2.5">
            <Settings className="w-5 h-5 text-gray-600" />
            <h3 className="font-bold text-sm text-gray-800">
              Generation Options
            </h3>
          </div>
          <div className="p-5 space-y-5">
            {/* Include Uncommon Tests Toggle */}
            <div className="flex items-center justify-between py-3 px-4 bg-gray-50 rounded-xl border border-gray-200">
              <div className="flex items-center gap-3">
                <Sparkles className="w-4 h-4 text-violet-500" />
                <div>
                  <p className="text-sm font-medium text-gray-700">
                    Include uncommon tests
                  </p>
                  <p className="text-xs text-gray-400">
                    Edge cases and less common attack vectors
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIncludeUncommon(!includeUncommon)}
                className="flex-shrink-0"
              >
                {includeUncommon ? (
                  <ToggleRight className="w-8 h-8 text-violet-500" />
                ) : (
                  <ToggleLeft className="w-8 h-8 text-gray-400" />
                )}
              </button>
            </div>

            {/* Severity Filter */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-2.5">
                Severity Filter
              </label>
              <div className="flex flex-wrap gap-2">
                {SEVERITY_LEVELS.map((severity) => {
                  const isActive = severityFilter[severity.id];
                  return (
                    <button
                      key={severity.id}
                      onClick={() => toggleSeverity(severity.id)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-xl border-2 text-sm font-medium transition-all ${
                        isActive
                          ? "border-gray-800 bg-gray-800 text-white shadow-sm"
                          : "border-gray-200 bg-white text-gray-400 hover:border-gray-300"
                      }`}
                    >
                      <span
                        className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${severity.color}`}
                      />
                      {severity.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Suite Name */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Suite Name
                <span className="text-gray-300 ml-1">(optional)</span>
              </label>
              <input
                type="text"
                value={suiteName}
                onChange={(e) => setSuiteName(e.target.value)}
                placeholder="e.g. IoT Network Audit Q1"
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
              />
            </div>

            {/* AutoML Framework Selector */}
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                AutoML Framework
              </label>
              <select
                value={automlTool}
                onChange={(e) => setAutomlTool(e.target.value)}
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent bg-white"
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

            {/* Force New Suite Toggle */}
            <div className="flex items-center justify-between py-3 px-4 bg-gray-50 rounded-xl border border-gray-200">
              <div className="flex items-center gap-3">
                <RefreshCw className="w-4 h-4 text-blue-500" />
                <div>
                  <p className="text-sm font-medium text-gray-700">
                    Force new suite
                  </p>
                  <p className="text-xs text-gray-400">
                    Create fresh instead of enhancing an existing matching suite
                  </p>
                </div>
              </div>
              <button
                onClick={() => setForceNew(!forceNew)}
                className="flex-shrink-0"
              >
                {forceNew ? (
                  <ToggleRight className="w-8 h-8 text-blue-500" />
                ) : (
                  <ToggleLeft className="w-8 h-8 text-gray-400" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* ---- Success Message ---- */}
        {generateSuccess && (
          <div className={`flex items-start gap-3 rounded-2xl px-5 py-4 shadow-sm ${
            generateSuccess.action === "enhanced"
              ? "bg-violet-50 border border-violet-200"
              : "bg-emerald-50 border border-emerald-200"
          }`}>
            {generateSuccess.action === "enhanced" ? (
              <Sparkles className="w-6 h-6 text-violet-500 flex-shrink-0 mt-0.5" />
            ) : (
              <CheckCircle2 className="w-6 h-6 text-emerald-500 flex-shrink-0 mt-0.5" />
            )}
            <div>
              <p className={`font-semibold text-sm ${
                generateSuccess.action === "enhanced" ? "text-violet-700" : "text-emerald-700"
              }`}>
                {generateSuccess.action === "enhanced"
                  ? `Suite enhanced with latest ML scores! (Enhancement #${generateSuccess.enhancementCount})`
                  : "Test suite generated successfully!"}
              </p>
              <div className="flex flex-wrap items-center gap-2 mt-1.5">
                <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-md font-semibold">
                  {generateSuccess.testCount} tests
                </span>
                {generateSuccess.recommendedCount > 0 && (
                  <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-md font-semibold">
                    {generateSuccess.recommendedCount} ML-recommended
                  </span>
                )}
                {generateSuccess.action === "enhanced" && generateSuccess.testsAdded > 0 && (
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-md font-semibold">
                    +{generateSuccess.testsAdded} new tests added
                  </span>
                )}
                {generateSuccess.suiteName && (
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-md font-mono">
                    {generateSuccess.suiteName}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ---- Error Message ---- */}
        {generateError && (
          <div className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-2xl px-5 py-4 shadow-sm">
            <XCircle className="w-6 h-6 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-red-700 text-sm">
                Generation failed
              </p>
              <p className="text-xs text-red-600 mt-1">{generateError}</p>
            </div>
          </div>
        )}

        {/* ---- Generate Button ---- */}
        <button
          onClick={handleGenerate}
          disabled={!canGenerate || generating}
          className={`w-full py-4 rounded-2xl font-bold text-base flex items-center justify-center gap-3 shadow-lg transition-all active:scale-[0.99] text-white ${
            !canGenerate || generating
              ? "bg-gray-300 cursor-not-allowed shadow-none"
              : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-blue-200 hover:shadow-blue-300"
          }`}
        >
          {generating ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Generating Test Suite...
            </>
          ) : (
            <>
              <Zap className="w-5 h-5" />
              Generate Test Suite
              {selectedDeviceIds.size > 0 && selectedProtocols.size > 0 && (
                <span className="text-sm font-normal opacity-80">
                  ({selectedDeviceIds.size} devices, {selectedProtocols.size}{" "}
                  protocols)
                </span>
              )}
            </>
          )}
        </button>

        {/* Disabled hint */}
        {!canGenerate && !generating && (
          <p className="text-xs text-gray-400 text-center -mt-2">
            {selectedDeviceIds.size === 0
              ? "Select at least one device to generate tests"
              : selectedProtocols.size === 0
              ? "Select at least one protocol to generate tests"
              : "Enable at least one severity level"}
          </p>
        )}
      </div>
    </div>
  );
}
