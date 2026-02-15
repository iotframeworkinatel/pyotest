import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Monitor,
  Server,
  Cpu,
  Database,
  Radio,
  Settings,
  FileCode,
  Package,
  FolderOpen,
  TestTube,
  Shield,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Icon map for tech stack sections                                   */
/* ------------------------------------------------------------------ */
const SECTION_ICONS = {
  frontend: Monitor,
  backend: Server,
  scanner: Cpu,
  automl: Database,
  devices: Radio,
  infrastructure: Settings,
};

/* ------------------------------------------------------------------ */
/*  Color map                                                          */
/* ------------------------------------------------------------------ */
const COLOR_MAP = {
  blue: {
    bg: "bg-blue-50",
    border: "border-blue-200",
    badge: "bg-blue-100 text-blue-700 border-blue-200",
    icon_bg: "bg-blue-100",
    icon: "text-blue-600",
    header: "text-blue-800",
  },
  purple: {
    bg: "bg-purple-50",
    border: "border-purple-200",
    badge: "bg-purple-100 text-purple-700 border-purple-200",
    icon_bg: "bg-purple-100",
    icon: "text-purple-600",
    header: "text-purple-800",
  },
  green: {
    bg: "bg-green-50",
    border: "border-green-200",
    badge: "bg-green-100 text-green-700 border-green-200",
    icon_bg: "bg-green-100",
    icon: "text-green-600",
    header: "text-green-800",
  },
  amber: {
    bg: "bg-amber-50",
    border: "border-amber-200",
    badge: "bg-amber-100 text-amber-700 border-amber-200",
    icon_bg: "bg-amber-100",
    icon: "text-amber-600",
    header: "text-amber-800",
  },
  red: {
    bg: "bg-red-50",
    border: "border-red-200",
    badge: "bg-red-100 text-red-700 border-red-200",
    icon_bg: "bg-red-100",
    icon: "text-red-600",
    header: "text-red-800",
  },
  gray: {
    bg: "bg-gray-50",
    border: "border-gray-200",
    badge: "bg-gray-100 text-gray-700 border-gray-200",
    icon_bg: "bg-gray-100",
    icon: "text-gray-600",
    header: "text-gray-800",
  },
};

/* ------------------------------------------------------------------ */
/*  Technology badge                                                   */
/* ------------------------------------------------------------------ */
function TechBadge({ tech, colorKey }) {
  const colors = COLOR_MAP[colorKey] || COLOR_MAP.gray;
  return (
    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium ${colors.badge}`}>
      <Package className="w-3 h-3 opacity-60" />
      <span>{tech.name}</span>
      {tech.version && tech.version !== "latest" && tech.version !== "N/A" && (
        <span className="opacity-50 text-[10px]">v{tech.version}</span>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Protocol card (for scanner protocols)                              */
/* ------------------------------------------------------------------ */
function ProtocolCard({ name, protocol }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-gray-50 transition"
      >
        <Shield className="w-4 h-4 text-green-500 shrink-0" />
        <span className="text-xs font-semibold text-gray-700">{name}</span>
        <span className="text-[10px] text-gray-400 ml-1">port {protocol.port}</span>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[10px] bg-green-50 text-green-600 px-2 py-0.5 rounded-full border border-green-200">
            {protocol.static_tests} static
          </span>
          <span className="text-[10px] bg-amber-50 text-amber-600 px-2 py-0.5 rounded-full border border-amber-200">
            {protocol.adaptive_tests} adaptive
          </span>
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-gray-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 border-t border-gray-100 pt-2 space-y-2">
          <p className="text-[11px] text-gray-500">{protocol.description}</p>

          {/* Static tests */}
          {protocol.static_test_ids && protocol.static_test_ids.length > 0 && (
            <div>
              <h6 className="text-[10px] font-semibold text-green-600 mb-1 flex items-center gap-1">
                <TestTube className="w-3 h-3" /> Static Tests
              </h6>
              <div className="flex flex-wrap gap-1">
                {protocol.static_test_ids.map((id) => (
                  <code
                    key={id}
                    className="text-[10px] font-mono bg-green-50 text-green-700 px-2 py-0.5 rounded border border-green-200"
                  >
                    {id}
                  </code>
                ))}
              </div>
            </div>
          )}

          {/* Adaptive tests */}
          {protocol.adaptive_test_ids && protocol.adaptive_test_ids.length > 0 && (
            <div>
              <h6 className="text-[10px] font-semibold text-amber-600 mb-1 flex items-center gap-1">
                <TestTube className="w-3 h-3" /> Adaptive Tests (AutoML-only)
              </h6>
              <div className="flex flex-wrap gap-1">
                {protocol.adaptive_test_ids.map((id) => (
                  <code
                    key={id}
                    className="text-[10px] font-mono bg-amber-50 text-amber-700 px-2 py-0.5 rounded border border-amber-200"
                  >
                    {id}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Stack section (accordion)                                          */
/* ------------------------------------------------------------------ */
function StackSection({ sectionKey, section }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = SECTION_ICONS[sectionKey] || Settings;
  const colors = COLOR_MAP[section.color] || COLOR_MAP.gray;

  const techCount = section.technologies?.length || 0;
  const fileCount = section.files?.length || 0;

  return (
    <div className={`rounded-2xl border-2 ${colors.border} overflow-hidden transition-all`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center gap-4 p-4 text-left transition ${
          expanded ? colors.bg : "bg-white hover:bg-gray-50"
        }`}
      >
        <div className={`w-10 h-10 rounded-xl ${colors.icon_bg} flex items-center justify-center shrink-0`}>
          <Icon className={`w-5 h-5 ${colors.icon}`} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className={`font-semibold ${colors.header}`}>{section.label}</h3>
          <p className="text-xs text-gray-500 truncate mt-0.5">{section.description}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[10px] text-gray-400">{techCount} technologies</span>
          {expanded ? (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className={`px-4 pb-4 ${colors.bg} space-y-4`}>
          {/* Technologies */}
          <div>
            <h4 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Package className="w-3 h-3" /> Technologies
            </h4>
            <div className="flex flex-wrap gap-2">
              {(section.technologies || []).map((tech) => (
                <div key={tech.name} className="group relative">
                  <TechBadge tech={tech} colorKey={section.color} />
                  {/* Tooltip on hover */}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-10">
                    <div className="bg-gray-900 text-white text-[10px] px-3 py-1.5 rounded-lg whitespace-nowrap shadow-lg">
                      {tech.role}
                      <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Technology details table */}
          <div className="bg-white/80 rounded-xl border border-gray-200/80 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Technology</th>
                  <th className="text-left px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Version</th>
                  <th className="text-left px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Role</th>
                </tr>
              </thead>
              <tbody>
                {(section.technologies || []).map((tech, i) => (
                  <tr key={tech.name} className={i % 2 === 0 ? "" : "bg-gray-50/50"}>
                    <td className="px-3 py-2 font-medium text-gray-700">{tech.name}</td>
                    <td className="px-3 py-2 font-mono text-gray-500">{tech.version}</td>
                    <td className="px-3 py-2 text-gray-500">{tech.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Files */}
          {section.files && section.files.length > 0 && (
            <div>
              <h4 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <FolderOpen className="w-3 h-3" /> Key Files & Directories
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {section.files.map((file) => (
                  <code
                    key={file}
                    className="text-[10px] font-mono bg-white border border-gray-200 text-gray-600 px-2.5 py-1 rounded-lg flex items-center gap-1"
                  >
                    <FileCode className="w-3 h-3 text-gray-400" />
                    {file}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main TechStack component                                           */
/* ------------------------------------------------------------------ */
export default function TechStack({ metadata }) {
  const techStack = metadata?.tech_stack || {};
  const protocols = metadata?.protocols || {};

  // Compute totals
  const totalTech = Object.values(techStack).reduce(
    (sum, section) => sum + (section.technologies?.length || 0),
    0
  );
  const totalStaticTests = Object.values(protocols).reduce((s, p) => s + p.static_tests, 0);
  const totalAdaptiveTests = Object.values(protocols).reduce((s, p) => s + p.adaptive_tests, 0);

  return (
    <div className="space-y-4">
      {/* Summary header */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h3 className="font-semibold text-gray-800 mb-3">Technology Stack Overview</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-gray-50 rounded-lg p-3 text-center">
            <div className="text-xl font-bold text-gray-700">{Object.keys(techStack).length}</div>
            <div className="text-[10px] text-gray-500">Components</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-3 text-center">
            <div className="text-xl font-bold text-gray-700">{totalTech}</div>
            <div className="text-[10px] text-gray-500">Technologies</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-3 text-center">
            <div className="text-xl font-bold text-gray-700">{Object.keys(protocols).length}</div>
            <div className="text-[10px] text-gray-500">Protocols</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-3 text-center">
            <div className="text-xl font-bold text-gray-700">{totalStaticTests + totalAdaptiveTests}</div>
            <div className="text-[10px] text-gray-500">Vulnerability Tests</div>
          </div>
        </div>
      </div>

      {/* Stack sections */}
      <div className="space-y-3">
        {Object.entries(techStack).map(([key, section]) => (
          <StackSection key={key} sectionKey={key} section={section} />
        ))}
      </div>

      {/* Protocol test registry */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h3 className="font-semibold text-gray-800 mb-1">Vulnerability Test Registry</h3>
        <p className="text-xs text-gray-500 mb-4">
          {totalStaticTests} static tests (always run) + {totalAdaptiveTests} adaptive tests (AutoML-selected only) across {Object.keys(protocols).length} protocols
        </p>
        <div className="space-y-2">
          {Object.entries(protocols).map(([name, protocol]) => (
            <ProtocolCard key={name} name={name} protocol={protocol} />
          ))}
        </div>
      </div>
    </div>
  );
}
