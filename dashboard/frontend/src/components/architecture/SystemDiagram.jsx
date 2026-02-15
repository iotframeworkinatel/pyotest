import { useState } from "react";
import {
  Monitor,
  Server,
  Database,
  Cpu,
  Radio,
  ArrowDown,
  ChevronDown,
  ChevronUp,
  X,
  Globe,
  Shield,
  Wifi,
  Lock,
  Eye,
  Podcast,
  Hexagon,
  Cable,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Helper: protocol icon                                              */
/* ------------------------------------------------------------------ */
const PROTO_ICONS = {
  FTP: Lock,
  HTTP: Globe,
  SSH: Shield,
  Telnet: Cable,
  MQTT: Wifi,
  RTSP: Eye,
  CoAP: Podcast,
  Modbus: Hexagon,
  DNS: Database,
};

/* ------------------------------------------------------------------ */
/*  Tailwind-safe color map (JIT requires full class strings)          */
/* ------------------------------------------------------------------ */
const LAYER_COLORS = {
  blue: { wrapper: "border-blue-200 bg-blue-50/50", icon_bg: "bg-blue-100", icon: "text-blue-600", title: "text-blue-800" },
  purple: { wrapper: "border-purple-200 bg-purple-50/50", icon_bg: "bg-purple-100", icon: "text-purple-600", title: "text-purple-800" },
  green: { wrapper: "border-green-200 bg-green-50/50", icon_bg: "bg-green-100", icon: "text-green-600", title: "text-green-800" },
  amber: { wrapper: "border-amber-200 bg-amber-50/50", icon_bg: "bg-amber-100", icon: "text-amber-600", title: "text-amber-800" },
  red: { wrapper: "border-red-200 bg-red-50/50", icon_bg: "bg-red-100", icon: "text-red-600", title: "text-red-800" },
};

/* ------------------------------------------------------------------ */
/*  Layer card component                                               */
/* ------------------------------------------------------------------ */
function LayerCard({ color, title, subtitle, icon: Icon, children, className = "" }) {
  const c = LAYER_COLORS[color] || LAYER_COLORS.blue;
  return (
    <div className={`rounded-2xl border-2 ${c.wrapper} p-5 ${className}`}>
      <div className="flex items-center gap-3 mb-4">
        <div className={`w-9 h-9 rounded-lg ${c.icon_bg} flex items-center justify-center`}>
          <Icon className={`w-5 h-5 ${c.icon}`} />
        </div>
        <div>
          <h3 className={`font-semibold ${c.title}`}>{title}</h3>
          {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
        </div>
      </div>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Arrow connector between layers                                     */
/* ------------------------------------------------------------------ */
function LayerConnector({ label }) {
  return (
    <div className="flex flex-col items-center py-2 text-gray-400">
      <div className="w-px h-4 bg-gray-300" />
      <ArrowDown className="w-4 h-4" />
      {label && (
        <span className="text-[10px] font-medium text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full mt-1">
          {label}
        </span>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Container badge (clickable)                                        */
/* ------------------------------------------------------------------ */
function ContainerBadge({ container, onClick, isSelected }) {
  const roleColors = {
    vulnerable_device: "border-red-200 bg-red-50 text-red-700 hover:bg-red-100",
    infrastructure: "border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100",
  };
  const cls = roleColors[container.role] || roleColors.infrastructure;

  return (
    <button
      onClick={onClick}
      className={`text-left px-3 py-2 rounded-lg border text-xs font-mono transition-all ${cls} ${
        isSelected ? "ring-2 ring-blue-400 shadow-md" : ""
      }`}
    >
      <span className="font-semibold">{container.name}</span>
      {container.ip && (
        <span className="ml-2 text-[10px] opacity-60">{container.ip}</span>
      )}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Detail panel (slide out when container clicked)                    */
/* ------------------------------------------------------------------ */
function DetailPanel({ container, onClose }) {
  if (!container) return null;
  const ProtoIcon = PROTO_ICONS[container.protocol] || Radio;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-lg p-5 animate-in fade-in duration-200">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
            <ProtoIcon className="w-5 h-5 text-blue-600" />
          </div>
          <div>
            <h4 className="font-semibold text-gray-800">{container.name}</h4>
            <p className="text-xs text-gray-500">{container.role === "vulnerable_device" ? "Vulnerable IoT Device" : "Infrastructure Service"}</p>
          </div>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg transition">
          <X className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      <p className="text-sm text-gray-600 mb-4">{container.description}</p>

      <div className="grid grid-cols-2 gap-3 text-xs">
        {container.ip && (
          <div className="bg-gray-50 rounded-lg p-2.5">
            <span className="text-gray-400 block mb-0.5">IP Address</span>
            <span className="font-mono font-medium text-gray-700">{container.ip}</span>
          </div>
        )}
        {container.ports && container.ports.length > 0 && (
          <div className="bg-gray-50 rounded-lg p-2.5">
            <span className="text-gray-400 block mb-0.5">Ports</span>
            <span className="font-mono font-medium text-gray-700">{container.ports.join(", ")}</span>
          </div>
        )}
        {container.protocol && (
          <div className="bg-gray-50 rounded-lg p-2.5">
            <span className="text-gray-400 block mb-0.5">Protocol</span>
            <span className="font-medium text-gray-700">{container.protocol}</span>
          </div>
        )}
        <div className="bg-gray-50 rounded-lg p-2.5">
          <span className="text-gray-400 block mb-0.5">Technology</span>
          <span className="font-medium text-gray-700">{container.tech}</span>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main SystemDiagram component                                       */
/* ------------------------------------------------------------------ */
export default function SystemDiagram({ metadata }) {
  const [selectedContainer, setSelectedContainer] = useState(null);
  const [expandedDevices, setExpandedDevices] = useState(false);

  const containers = metadata?.containers || [];
  const infra = containers.filter((c) => c.role === "infrastructure");
  const devices = containers.filter((c) => c.role === "vulnerable_device");

  // Group devices by protocol
  const devicesByProtocol = {};
  devices.forEach((d) => {
    const proto = d.protocol || "Other";
    if (!devicesByProtocol[proto]) devicesByProtocol[proto] = [];
    devicesByProtocol[proto].push(d);
  });

  const frontend = infra.find((c) => c.name === "dashboard_ui");
  const backend = infra.find((c) => c.name === "dashboard_api");
  const scanner = infra.find((c) => c.name === "scanner");
  const h2o = infra.find((c) => c.name === "h2o-automl");

  return (
    <div className="space-y-4">
      {/* Network badge */}
      <div className="flex items-center justify-end">
        <span className="text-[10px] font-mono bg-gray-100 text-gray-500 px-3 py-1 rounded-full border border-gray-200">
          Docker Bridge Network: 172.20.0.0/24
        </span>
      </div>

      {/* Layer 1: Frontend */}
      <LayerCard
        color="blue"
        title="Frontend Layer"
        subtitle="User-facing dashboard application"
        icon={Monitor}
      >
        <div className="flex flex-wrap gap-2">
          {frontend && (
            <ContainerBadge
              container={frontend}
              onClick={() => setSelectedContainer(frontend)}
              isSelected={selectedContainer?.name === frontend.name}
            />
          )}
          <div className="flex flex-wrap gap-1.5 items-center ml-4">
            {["React 18", "Vite 5", "Tailwind CSS", "Recharts", "Lucide"].map((t) => (
              <span key={t} className="text-[10px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                {t}
              </span>
            ))}
          </div>
        </div>
      </LayerCard>

      <LayerConnector label="HTTP / Axios" />

      {/* Layer 2: Backend API */}
      <LayerCard
        color="purple"
        title="Backend API Layer"
        subtitle="REST API serving dashboard data"
        icon={Server}
      >
        <div className="flex flex-wrap gap-2">
          {backend && (
            <ContainerBadge
              container={backend}
              onClick={() => setSelectedContainer(backend)}
              isSelected={selectedContainer?.name === backend.name}
            />
          )}
          <div className="flex flex-wrap gap-1.5 items-center ml-4">
            {["FastAPI", "Docker SDK", "Pandas", "SciPy", "NumPy"].map((t) => (
              <span key={t} className="text-[10px] bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium">
                {t}
              </span>
            ))}
          </div>
        </div>
        <div className="mt-3 text-[10px] text-purple-600 font-medium">
          {metadata?.api_endpoints?.length || 0} REST endpoints &middot; Port 8000
        </div>
      </LayerCard>

      <LayerConnector label="Docker exec" />

      {/* Layer 3: Scanner + AutoML */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <LayerCard
          color="green"
          title="Scanner Engine"
          subtitle="Vulnerability testing core"
          icon={Cpu}
        >
          {scanner && (
            <div className="mb-3">
              <ContainerBadge
                container={scanner}
                onClick={() => setSelectedContainer(scanner)}
                isSelected={selectedContainer?.name === scanner.name}
              />
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {["python-nmap", "requests", "paramiko", "paho-mqtt", "aiocoap", "pymodbus"].map((t) => (
              <span key={t} className="text-[10px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                {t}
              </span>
            ))}
          </div>
          <div className="mt-3 text-[10px] text-green-600 font-medium">
            {metadata?.protocols
              ? `${Object.values(metadata.protocols).reduce((s, p) => s + p.static_tests, 0)} static + ${Object.values(metadata.protocols).reduce((s, p) => s + p.adaptive_tests, 0)} adaptive tests`
              : "58 vulnerability tests"}{" "}
            &middot; 9 protocols
          </div>
        </LayerCard>

        <LayerCard
          color="amber"
          title="H2O AutoML"
          subtitle="Machine learning pipeline"
          icon={Database}
        >
          {h2o && (
            <div className="mb-3">
              <ContainerBadge
                container={h2o}
                onClick={() => setSelectedContainer(h2o)}
                isSelected={selectedContainer?.name === h2o.name}
              />
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {["H2O-3", "GBM", "GLM", "XGBoost", "DeepLearning", "StackedEnsemble"].map((t) => (
              <span key={t} className="text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
                {t}
              </span>
            ))}
          </div>
          <div className="mt-3 text-[10px] text-amber-600 font-medium">
            Binary classifier &middot; Port 54321 &middot; 5min training
          </div>
        </LayerCard>
      </div>

      <LayerConnector label="TCP / UDP (9 protocols)" />

      {/* Layer 4: Vulnerable Devices */}
      <LayerCard
        color="red"
        title="Vulnerable IoT Device Layer"
        subtitle={`${devices.length} intentionally vulnerable containers`}
        icon={Radio}
      >
        <div className="space-y-3">
          {Object.entries(devicesByProtocol).map(([proto, devs]) => {
            const ProtoIcon = PROTO_ICONS[proto] || Radio;
            return (
              <div key={proto}>
                <div className="flex items-center gap-2 mb-1.5">
                  <ProtoIcon className="w-3.5 h-3.5 text-red-500" />
                  <span className="text-xs font-semibold text-red-700">{proto}</span>
                  <span className="text-[10px] text-red-400">({devs.length})</span>
                </div>
                <div className="flex flex-wrap gap-2 ml-6">
                  {devs.map((d) => (
                    <ContainerBadge
                      key={d.name}
                      container={d}
                      onClick={() => setSelectedContainer(d)}
                      isSelected={selectedContainer?.name === d.name}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </LayerCard>

      {/* Detail panel */}
      {selectedContainer && (
        <div className="mt-4">
          <DetailPanel
            container={selectedContainer}
            onClose={() => setSelectedContainer(null)}
          />
        </div>
      )}
    </div>
  );
}
