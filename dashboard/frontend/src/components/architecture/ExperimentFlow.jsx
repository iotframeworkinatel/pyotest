import { useState } from "react";
import {
  Radar,
  Shield,
  Brain,
  ListChecks,
  Zap,
  Shuffle,
  BarChart3,
  ChevronDown,
  ChevronUp,
  ArrowDown,
  FileText,
  FolderOpen,
  Code,
  ArrowRight,
  CheckCircle2,
  GitBranch,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Icon map (matches backend phase.icon strings)                      */
/* ------------------------------------------------------------------ */
const ICON_MAP = {
  Radar,
  Shield,
  Brain,
  ListChecks,
  Zap,
  Shuffle,
  BarChart3,
};

/* ------------------------------------------------------------------ */
/*  Color map                                                          */
/* ------------------------------------------------------------------ */
const COLOR_MAP = {
  blue: {
    bg: "bg-blue-50",
    border: "border-blue-200",
    icon_bg: "bg-blue-100",
    icon: "text-blue-600",
    badge: "bg-blue-100 text-blue-700",
    line: "bg-blue-300",
    number: "bg-blue-600 text-white",
    ring: "ring-blue-200",
  },
  green: {
    bg: "bg-green-50",
    border: "border-green-200",
    icon_bg: "bg-green-100",
    icon: "text-green-600",
    badge: "bg-green-100 text-green-700",
    line: "bg-green-300",
    number: "bg-green-600 text-white",
    ring: "ring-green-200",
  },
  purple: {
    bg: "bg-purple-50",
    border: "border-purple-200",
    icon_bg: "bg-purple-100",
    icon: "text-purple-600",
    badge: "bg-purple-100 text-purple-700",
    line: "bg-purple-300",
    number: "bg-purple-600 text-white",
    ring: "ring-purple-200",
  },
  amber: {
    bg: "bg-amber-50",
    border: "border-amber-200",
    icon_bg: "bg-amber-100",
    icon: "text-amber-600",
    badge: "bg-amber-100 text-amber-700",
    line: "bg-amber-300",
    number: "bg-amber-600 text-white",
    ring: "ring-amber-200",
  },
  gray: {
    bg: "bg-gray-50",
    border: "border-gray-200",
    icon_bg: "bg-gray-100",
    icon: "text-gray-600",
    badge: "bg-gray-100 text-gray-700",
    line: "bg-gray-300",
    number: "bg-gray-600 text-white",
    ring: "ring-gray-200",
  },
};

/* ------------------------------------------------------------------ */
/*  Flow connector                                                     */
/* ------------------------------------------------------------------ */
function FlowConnector({ color = "gray" }) {
  return (
    <div className="flex flex-col items-center py-1">
      <div className={`w-0.5 h-6 ${COLOR_MAP[color]?.line || "bg-gray-300"}`} />
      <ArrowDown className="w-4 h-4 text-gray-400" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Decision gate (diamond shaped)                                     */
/* ------------------------------------------------------------------ */
function DecisionGate() {
  return (
    <div className="flex flex-col items-center py-1">
      <div className="w-0.5 h-4 bg-gray-300" />
      <div className="relative">
        <div className="w-32 h-16 bg-yellow-50 border-2 border-yellow-300 rotate-45 rounded-lg" />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[11px] font-semibold text-yellow-700 text-center leading-tight">
            AutoML<br />mode?
          </span>
        </div>
      </div>
      <div className="flex items-center gap-6 mt-2">
        <div className="flex items-center gap-1">
          <span className="text-[10px] font-medium text-gray-400">No</span>
          <ArrowRight className="w-3 h-3 text-gray-300" />
          <span className="text-[10px] bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">END (static only)</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[10px] font-medium text-green-500">Yes</span>
          <ArrowDown className="w-3 h-3 text-green-400" />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Phase card                                                         */
/* ------------------------------------------------------------------ */
function PhaseCard({ phase, index, isLast }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = ICON_MAP[phase.icon] || Shield;
  const colors = COLOR_MAP[phase.color] || COLOR_MAP.gray;

  return (
    <div className="flex flex-col items-center w-full">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full max-w-2xl rounded-2xl border-2 ${colors.border} ${colors.bg} p-4 transition-all hover:shadow-md text-left ${
          expanded ? `ring-2 ${colors.ring} shadow-md` : ""
        }`}
      >
        <div className="flex items-start gap-4">
          {/* Phase number */}
          <div className={`w-8 h-8 rounded-full ${colors.number} flex items-center justify-center text-xs font-bold shrink-0`}>
            {phase.id}
          </div>

          {/* Icon */}
          <div className={`w-10 h-10 rounded-xl ${colors.icon_bg} flex items-center justify-center shrink-0`}>
            <Icon className={`w-5 h-5 ${colors.icon}`} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-semibold text-gray-800 text-sm">{phase.name}</h4>
              {expanded ? (
                <ChevronUp className="w-4 h-4 text-gray-400 shrink-0" />
              ) : (
                <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
              )}
            </div>
            <p className="text-xs text-gray-500 leading-relaxed">{phase.description}</p>
          </div>
        </div>

        {/* Expanded details */}
        {expanded && (
          <div className="mt-4 ml-12 space-y-3 border-t border-gray-200/50 pt-4" onClick={(e) => e.stopPropagation()}>
            {/* Detailed description */}
            <p className="text-xs text-gray-600 leading-relaxed bg-white/60 rounded-lg p-3">
              {phase.details}
            </p>

            {/* Inputs */}
            {phase.inputs && phase.inputs.length > 0 && (
              <div>
                <h5 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                  <FolderOpen className="w-3 h-3" /> Inputs
                </h5>
                <div className="flex flex-wrap gap-1.5">
                  {phase.inputs.map((input, i) => (
                    <span
                      key={i}
                      className="text-[10px] bg-white border border-gray-200 text-gray-600 px-2.5 py-1 rounded-lg font-medium"
                    >
                      {input}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Outputs */}
            {phase.outputs && phase.outputs.length > 0 && (
              <div>
                <h5 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                  <FileText className="w-3 h-3" /> Outputs
                </h5>
                <div className="flex flex-wrap gap-1.5">
                  {phase.outputs.map((output, i) => (
                    <span
                      key={i}
                      className={`text-[10px] ${colors.badge} px-2.5 py-1 rounded-lg font-medium`}
                    >
                      {output}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Source module */}
            {phase.module && (
              <div className="flex items-center gap-2">
                <Code className="w-3 h-3 text-gray-400" />
                <code className="text-[10px] font-mono text-gray-500 bg-white/80 px-2 py-1 rounded">
                  {phase.module}
                </code>
              </div>
            )}
          </div>
        )}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main ExperimentFlow component                                      */
/* ------------------------------------------------------------------ */
export default function ExperimentFlow({ metadata }) {
  const phases = metadata?.experiment_phases || [];

  // Split phases into pre-decision and post-decision
  const preDecision = phases.filter((p) => p.id <= 2);
  const postDecision = phases.filter((p) => p.id >= 3);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-purple-50 flex items-center justify-center">
            <GitBranch className="w-5 h-5 text-purple-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-800">Experiment Pipeline</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              PhD thesis methodology: AutoML-guided adaptive vulnerability testing for IoT devices.
              Click each phase to see details, inputs/outputs, and source modules.
            </p>
          </div>
        </div>
      </div>

      {/* Flow diagram */}
      <div className="flex flex-col items-center space-y-0">
        {/* START node */}
        <div className="flex items-center gap-2 mb-2">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span className="text-xs font-semibold text-green-600 uppercase tracking-wider">Start</span>
        </div>

        {/* Pre-decision phases (1-2) */}
        {preDecision.map((phase, i) => (
          <div key={phase.id} className="w-full flex flex-col items-center">
            <FlowConnector color={phase.color} />
            <PhaseCard phase={phase} index={i} />
          </div>
        ))}

        {/* Decision gate */}
        <DecisionGate />

        {/* Post-decision phases (3-7) */}
        {postDecision.map((phase, i) => (
          <div key={phase.id} className="w-full flex flex-col items-center">
            <FlowConnector color={phase.color} />
            <PhaseCard phase={phase} index={i + preDecision.length} isLast={i === postDecision.length - 1} />
          </div>
        ))}

        {/* END node */}
        <div className="flex flex-col items-center pt-2">
          <div className="w-0.5 h-4 bg-gray-300" />
          <ArrowDown className="w-4 h-4 text-gray-400" />
          <div className="flex items-center gap-2 mt-2">
            <CheckCircle2 className="w-5 h-5 text-blue-500" />
            <span className="text-xs font-semibold text-blue-600 uppercase tracking-wider">Complete</span>
          </div>
          <p className="text-[10px] text-gray-400 mt-1 text-center max-w-xs">
            Results available in Dashboard History and Statistical Analysis tabs
          </p>
        </div>
      </div>

      {/* Legend */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mt-6">
        <h4 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">Legend</h4>
        <div className="flex flex-wrap gap-4">
          {[
            { color: "blue", label: "Network Scan / Analysis" },
            { color: "green", label: "Static Testing" },
            { color: "purple", label: "Machine Learning" },
            { color: "amber", label: "Adaptive Testing" },
            { color: "gray", label: "Random Baseline (Control)" },
          ].map(({ color, label }) => (
            <div key={color} className="flex items-center gap-1.5">
              <div className={`w-3 h-3 rounded-full ${COLOR_MAP[color].number.split(" ")[0]}`} />
              <span className="text-[10px] text-gray-500">{label}</span>
            </div>
          ))}
        </div>

        {/* Expected results summary */}
        <div className="mt-4 pt-3 border-t border-gray-100">
          <h4 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Expected Results</h4>
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-green-50 rounded-lg p-2.5 text-center">
              <div className="text-lg font-bold text-green-700">~28</div>
              <div className="text-[10px] text-green-600">Static vulns</div>
            </div>
            <div className="bg-purple-50 rounded-lg p-2.5 text-center">
              <div className="text-lg font-bold text-purple-700">~48</div>
              <div className="text-[10px] text-purple-600">AutoML vulns</div>
              <div className="text-[9px] text-purple-400 mt-0.5">+71% improvement</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-2.5 text-center">
              <div className="text-lg font-bold text-gray-700">~35</div>
              <div className="text-[10px] text-gray-600">Random vulns</div>
            </div>
          </div>
          <p className="text-[10px] text-gray-400 text-center mt-2">
            Hypothesis: AutoML &gt; Random &gt; Static (proves model intelligence matters)
          </p>
        </div>
      </div>
    </div>
  );
}
