import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { fetchStatisticalAnalysis, fetchLearningCurve, fetchModelMetrics } from "../api/experiments";
import RocCurveChart from "./charts/RocCurveChart";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  ReferenceLine,
  Cell,
} from "recharts";
import {
  FlaskConical,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  TrendingUp,
  BarChart3,
  Info,
  RefreshCw,
  BookOpen,
  Timer,
  Shield,
  BrainCircuit,
  ChevronDown,
  ChevronUp,
  Shuffle,
  Gauge,
  GraduationCap,
  HelpCircle,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatP(p) {
  if (p === null || p === undefined) return "—";
  if (p < 0.0001) return p.toExponential(2);
  return p.toFixed(6);
}

/**
 * InfoTooltip — hover icon that reveals an educational popover explaining
 * statistical concepts. Uses a portal so the tooltip is never clipped by
 * parent overflow-hidden containers.
 */
function InfoTooltip({ title, children }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const iconRef = useRef(null);

  const updatePos = useCallback(() => {
    if (!iconRef.current) return;
    const rect = iconRef.current.getBoundingClientRect();
    setPos({
      top: rect.top + window.scrollY,
      left: rect.left + rect.width / 2,
    });
  }, []);

  const handleEnter = () => {
    updatePos();
    setShow(true);
  };

  return (
    <>
      <span
        ref={iconRef}
        className="inline-flex items-center ml-1"
        onMouseEnter={handleEnter}
        onMouseLeave={() => setShow(false)}
      >
        <HelpCircle className={`w-3.5 h-3.5 cursor-help transition-colors ${show ? "text-violet-500" : "text-gray-400"}`} />
      </span>
      {show &&
        createPortal(
          <span
            className="pointer-events-none fixed z-[9999] w-72
              bg-gray-900 text-white text-xs leading-relaxed rounded-xl shadow-xl
              px-4 py-3 animate-in fade-in duration-150"
            style={{
              top: pos.top - 8,
              left: pos.left,
              transform: "translate(-50%, -100%)",
              position: "absolute",
            }}
          >
            {title && (
              <span className="block font-bold text-violet-300 mb-1">{title}</span>
            )}
            {children}
            <span className="absolute top-full left-1/2 -translate-x-1/2 border-[6px] border-transparent border-t-gray-900" />
          </span>,
          document.body
        )}
    </>
  );
}

function significanceBadge(reject, p) {
  if (reject === null || reject === undefined) return null;
  if (reject) {
    const stars = p < 0.001 ? "***" : p < 0.01 ? "**" : "*";
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700 border border-emerald-300">
        <CheckCircle2 className="w-3.5 h-3.5" />
        Significativo {stars}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-gray-100 text-gray-500 border border-gray-300">
      Não significativo
    </span>
  );
}

function StatRow({ label, value, sub }) {
  return (
    <div className="flex justify-between items-baseline py-1.5 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-600">{label}</span>
      <div className="text-right">
        <span className="font-semibold text-gray-800 font-mono text-sm">{value}</span>
        {sub && <p className="text-[10px] text-gray-400">{sub}</p>}
      </div>
    </div>
  );
}

/** Small reusable card for a paired comparison result */
function ComparisonCard({ title, subtitle, testResult, effectSize }) {
  if (!testResult) return null;
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <h4 className="text-sm font-semibold text-gray-700">{title}</h4>
        {significanceBadge(testResult.reject_h0, testResult.p_value)}
      </div>
      {subtitle && (
        <p className="text-xs text-gray-500 mb-3">{subtitle}</p>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider">Teste</p>
          <p className="font-semibold text-gray-800 text-xs">{testResult.test_name}</p>
        </div>
        <div className="bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider">Estatística</p>
          <p className="font-semibold text-gray-800 font-mono text-sm">
            {testResult.statistic !== null && testResult.statistic !== undefined
              ? testResult.statistic.toFixed(4)
              : "—"}
          </p>
        </div>
        <div className="bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider">p-value</p>
          <p className={`font-semibold font-mono text-sm ${testResult.reject_h0 ? "text-emerald-600" : "text-gray-800"}`}>
            {formatP(testResult.p_value)}
          </p>
        </div>
        {effectSize && (
          <div className="bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider">Cohen's d</p>
            <p className="font-semibold text-gray-800 font-mono text-sm">{effectSize.cohens_d ?? "—"}</p>
            <p className="text-[10px] text-gray-400 capitalize">{effectSize.interpretation ?? ""}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function StatisticalAnalysis() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showRawPairs, setShowRawPairs] = useState(false);
  const [learningCurve, setLearningCurve] = useState([]);
  const [lcStability, setLcStability] = useState(null);
  const [modelMetrics, setModelMetrics] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [res, lcRes, mmRes] = await Promise.all([
        fetchStatisticalAnalysis(),
        fetchLearningCurve().catch(() => ({ curve: [] })),
        fetchModelMetrics().catch(() => null),
      ]);
      if (res.error) {
        setError(res.error);
      }
      setData(res);
      setLearningCurve(lcRes.curve || []);
      setLcStability(lcRes.stability || null);
      setModelMetrics(mmRes);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // -- Loading --
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-gray-500 gap-4">
        <Loader2 className="w-10 h-10 animate-spin text-violet-500" />
        <p className="text-sm">Carregando análise estatística...</p>
      </div>
    );
  }

  // -- Error --
  if (error) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 flex items-start gap-4">
          <AlertTriangle className="w-6 h-6 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-red-700">Erro na análise</p>
            <p className="text-sm text-red-600 mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  const hasEnoughData = data && data.sample_size >= 2;
  const desc = data?.descriptive;
  const primary = data?.primary_test;
  const effect = data?.effect_size;
  const ci = data?.confidence_interval;
  const normality = data?.normality_test;
  const independent = data?.independent_test;
  const perProtocol = data?.per_protocol || [];
  const execTime = data?.execution_time;
  const conclusion = data?.conclusion;
  const rawPairs = data?.raw_pairs || [];
  const randomBaseline = data?.random_baseline;
  const hasRandom = !!randomBaseline && (data?.experiments_with_random ?? 0) > 0;
  const efficiency = data?.efficiency;
  const bootstrapCI = data?.confidence_interval_bootstrap;
  const powerAnalysis = data?.power_analysis;
  const permutationTest = data?.permutation_test;
  const varianceHomogeneity = data?.variance_homogeneity;
  const multipleComparison = data?.multiple_comparison_correction;

  // Chart data for paired observations
  const pairChartData = rawPairs.map((p, i) => ({
    name: `#${i + 1}`,
    static: p.static_vulns,
    automl: p.automl_vulns,
    ...(hasRandom && p.random_vulns !== undefined && p.random_vulns !== null
      ? { random: p.random_vulns }
      : {}),
    diff: p.automl_vulns - p.static_vulns,
  }));

  // Per-protocol chart data
  const protoChartData = perProtocol.map((p) => ({
    protocol: p.protocol.toUpperCase(),
    static_rate: +(p.static_rate * 100).toFixed(1),
    automl_rate: +(p.automl_rate * 100).toFixed(1),
    ...(hasRandom && p.random_rate !== undefined && p.random_rate !== null
      ? { random_rate: +(p.random_rate * 100).toFixed(1) }
      : {}),
  }));

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* =================== HEADER =================== */}
      <div className="bg-white shadow-lg rounded-2xl overflow-hidden border border-gray-200">
        <div className="bg-gradient-to-r from-violet-600 to-purple-600 px-6 py-5 flex items-center justify-between">
          <div className="flex items-center gap-3 text-white">
            <FlaskConical className="w-7 h-7" />
            <div>
              <h2 className="text-xl font-bold">Análise Estatística</h2>
              <p className="text-sm text-white/80">
                Teste de hipótese: PyoTest+AutoML vs. Suíte Estática
                {hasRandom && " vs. Baseline Aleatório"}
              </p>
            </div>
          </div>
          <button
            onClick={load}
            className="p-2 rounded-lg bg-white/20 hover:bg-white/30 text-white transition"
            title="Recarregar análise"
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>

        {/* Data status bar */}
        <div className="px-6 py-3 bg-gray-50 border-b border-gray-200 flex flex-wrap items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-violet-500" />
            <span className="text-gray-600">
              Experimentos pareados:{" "}
              <span className="font-bold text-gray-800">
                {data?.paired_experiments ?? 0}
              </span>
            </span>
          </div>
          {hasRandom && (
            <div className="flex items-center gap-2">
              <Shuffle className="w-4 h-4 text-amber-500" />
              <span className="text-gray-600">
                Com baseline aleatório:{" "}
                <span className="font-bold text-gray-800">
                  {data?.experiments_with_random ?? 0}
                </span>
              </span>
            </div>
          )}
          {data?.static_only_experiments > 0 && (
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-blue-500" />
              <span className="text-gray-600">
                Estáticos independentes:{" "}
                <span className="font-bold text-gray-800">
                  {data.static_only_experiments}
                </span>
              </span>
            </div>
          )}
          <div
            className={`ml-auto px-3 py-1 rounded-full text-xs font-semibold ${
              data?.sample_size >= 30
                ? "bg-emerald-100 text-emerald-700"
                : data?.sample_size >= 10
                ? "bg-amber-100 text-amber-700"
                : "bg-red-100 text-red-700"
            }`}
          >
            N = {data?.sample_size ?? 0}
            {data?.sample_size < 30 && " (recomendado: N ≥ 30)"}
          </div>
        </div>
      </div>

      {/* Insufficient data message */}
      {!hasEnoughData && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 flex items-start gap-4">
          <AlertTriangle className="w-6 h-6 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-amber-700">Dados insuficientes</p>
            <p className="text-sm text-amber-600 mt-1">
              {data?.message ||
                "São necessários pelo menos 2 experimentos pareados (com métricas static + automl) para executar a análise estatística."}
            </p>
            <p className="text-sm text-amber-600 mt-2">
              Use o modo <strong>Lote (Batch)</strong> no Dashboard para executar
              múltiplos experimentos automaticamente.
            </p>
          </div>
        </div>
      )}

      {hasEnoughData && (
        <>
          {/* =================== HYPOTHESIS CARD =================== */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Info className="w-4 h-4" />
              Hipótese
              <InfoTooltip title="Teste de Hipótese">
                O teste de hipótese compara duas suposições: a hipótese nula (H₀) assume que não há diferença entre os métodos, enquanto a hipótese alternativa (H₁) afirma que o AutoML detecta mais vulnerabilidades. Se o p-value for menor que 0.05, rejeitamos H₀ com 95% de confiança.
              </InfoTooltip>
            </h3>
            <div className={`grid grid-cols-1 ${hasRandom ? "md:grid-cols-3" : "md:grid-cols-2"} gap-4`}>
              <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <p className="text-xs font-bold text-gray-500 mb-1">H₀ (Nula)</p>
                <p className="text-sm text-gray-700">
                  A média de vulnerabilidades detectadas com <strong>AutoML</strong>{" "}
                  é <strong>igual</strong> à média com suíte estática.
                </p>
                <p className="text-xs text-gray-400 mt-2 font-mono">
                  μ<sub>automl</sub> = μ<sub>static</sub>
                </p>
              </div>
              <div className="bg-violet-50 rounded-xl p-4 border border-violet-200">
                <p className="text-xs font-bold text-violet-600 mb-1">
                  H₁ (Alternativa)
                </p>
                <p className="text-sm text-gray-700">
                  A média de vulnerabilidades detectadas com <strong>AutoML</strong>{" "}
                  é <strong>maior</strong> que com suíte estática.
                </p>
                <p className="text-xs text-violet-500 mt-2 font-mono">
                  μ<sub>automl</sub> &gt; μ<sub>static</sub>
                </p>
              </div>
              {hasRandom && (
                <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
                  <p className="text-xs font-bold text-amber-600 mb-1">
                    H₂ (Controle Aleatório)
                  </p>
                  <p className="text-sm text-gray-700">
                    O <strong>AutoML</strong> supera uma seleção{" "}
                    <strong>aleatória</strong> de testes adaptativos, provando que a
                    inteligência do modelo importa.
                  </p>
                  <p className="text-xs text-amber-500 mt-2 font-mono">
                    μ<sub>automl</sub> &gt; μ<sub>random</sub>
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* =================== DESCRIPTIVE STATISTICS =================== */}
          {desc && (
            <>
            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider flex items-center gap-2 -mb-3">
              <BarChart3 className="w-4 h-4" />
              Estatísticas Descritivas
              <InfoTooltip title="Estatísticas Descritivas">
                Resumo numérico dos dados: média (tendência central), mediana (valor central, robusta a outliers), desvio padrão (dispersão), mínimo e máximo. A coluna "Diferença" mostra AutoML menos Static para cada experimento pareado.
              </InfoTooltip>
            </h3>
            <div className={`grid grid-cols-1 ${hasRandom ? "md:grid-cols-4" : "md:grid-cols-3"} gap-4`}>
              {[
                {
                  title: "Suíte Estática",
                  icon: Shield,
                  headerCls: "bg-blue-50 border-b border-blue-100",
                  iconCls: "text-blue-500",
                  stats: desc.static,
                  show: true,
                },
                {
                  title: "Baseline Aleatório",
                  icon: Shuffle,
                  headerCls: "bg-amber-50 border-b border-amber-100",
                  iconCls: "text-amber-500",
                  stats: desc.random,
                  show: hasRandom && desc.random,
                },
                {
                  title: "AutoML",
                  icon: BrainCircuit,
                  headerCls: "bg-violet-50 border-b border-violet-100",
                  iconCls: "text-violet-500",
                  stats: desc.automl,
                  show: true,
                },
                {
                  title: "Diferença (AutoML − Static)",
                  icon: TrendingUp,
                  headerCls: "bg-emerald-50 border-b border-emerald-100",
                  iconCls: "text-emerald-500",
                  stats: desc.difference,
                  show: true,
                },
              ]
                .filter((c) => c.show)
                .map(({ title, icon: Icon, headerCls, iconCls, stats }) => (
                  <div
                    key={title}
                    className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden"
                  >
                    <div
                      className={`px-4 py-3 flex items-center gap-2 ${headerCls}`}
                    >
                      <Icon className={`w-4 h-4 ${iconCls}`} />
                      <h4 className="text-sm font-semibold text-gray-700">
                        {title}
                      </h4>
                    </div>
                    <div className="px-4 py-3 space-y-0">
                      <StatRow label="Média" value={stats?.mean ?? "—"} />
                      <StatRow label="Mediana" value={stats?.median ?? "—"} />
                      <StatRow label="Desvio Padrão" value={stats?.std ?? "—"} />
                      <StatRow label="Mínimo" value={stats?.min ?? "—"} />
                      <StatRow label="Máximo" value={stats?.max ?? "—"} />
                    </div>
                  </div>
                ))}
            </div>
            </>
          )}

          {/* =================== PRIMARY TEST (HERO) =================== */}
          {primary && (
            <div
              className={`rounded-2xl border-2 overflow-hidden shadow-lg ${
                primary.reject_h0
                  ? "border-emerald-400 bg-gradient-to-br from-emerald-50 to-green-50"
                  : "border-gray-300 bg-gradient-to-br from-gray-50 to-white"
              }`}
            >
              <div className="px-6 py-5 flex flex-col md:flex-row items-start md:items-center gap-6">
                {/* Left: Result icon */}
                <div
                  className={`w-20 h-20 rounded-2xl flex items-center justify-center flex-shrink-0 ${
                    primary.reject_h0
                      ? "bg-emerald-500 shadow-lg shadow-emerald-200"
                      : "bg-gray-300"
                  }`}
                >
                  {primary.reject_h0 ? (
                    <CheckCircle2 className="w-10 h-10 text-white" />
                  ) : (
                    <XCircle className="w-10 h-10 text-white" />
                  )}
                </div>

                {/* Center: Details */}
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-bold text-gray-800">
                      Resultado do Teste Primário
                      <InfoTooltip title="Teste Primário Pareado">
                        Compara as mesmas configurações de rede testadas com ambas as estratégias (pareado). Usa o t-test pareado se os dados seguem distribuição normal (Shapiro-Wilk p &gt; 0.05), ou o teste de Wilcoxon caso contrário. O teste é unilateral (one-sided): verifica se AutoML &gt; Static.
                      </InfoTooltip>
                    </h3>
                    {significanceBadge(primary.reject_h0, primary.p_value)}
                  </div>
                  <p className="text-sm text-gray-600 mb-3">
                    {primary.test_name}
                    {primary.df !== null && primary.df !== undefined && (
                      <span className="text-gray-400">
                        {" "}
                        (gl = {primary.df})
                      </span>
                    )}
                  </p>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-white/70 rounded-xl px-3 py-2 border border-gray-200">
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider flex items-center">
                        Estatística
                        <InfoTooltip>
                          Valor calculado pelo teste estatístico (t ou W). Quanto maior o valor absoluto, maior a evidência contra H₀.
                        </InfoTooltip>
                      </p>
                      <p className="font-bold text-gray-800 font-mono">
                        {primary.statistic !== null
                          ? primary.statistic.toFixed(4)
                          : "—"}
                      </p>
                    </div>
                    <div className="bg-white/70 rounded-xl px-3 py-2 border border-gray-200">
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider flex items-center">
                        p-value
                        <InfoTooltip title="p-value">
                          Probabilidade de observar resultados tão extremos quanto os obtidos, assumindo que H₀ é verdadeira. Se p &lt; 0.05, rejeitamos H₀ — evidência significativa de que AutoML supera a suíte estática.
                        </InfoTooltip>
                      </p>
                      <p
                        className={`font-bold font-mono ${
                          primary.reject_h0
                            ? "text-emerald-600"
                            : "text-gray-800"
                        }`}
                      >
                        {formatP(primary.p_value)}
                      </p>
                    </div>
                    <div className="bg-white/70 rounded-xl px-3 py-2 border border-gray-200">
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider flex items-center">
                        Cohen's d
                        <InfoTooltip title="Cohen's d (Tamanho do Efeito)">
                          Mede a magnitude prática da diferença, independente do tamanho da amostra. Interpretação: |d| &lt; 0.2 = negligenciável, 0.2-0.5 = pequeno, 0.5-0.8 = médio, &ge; 0.8 = grande. Um resultado pode ser estatisticamente significativo mas ter efeito prático pequeno.
                        </InfoTooltip>
                      </p>
                      <p className="font-bold text-gray-800 font-mono">
                        {effect?.cohens_d ?? "—"}
                      </p>
                      <p className="text-[10px] text-gray-400 capitalize">
                        {effect?.interpretation ?? ""}
                      </p>
                    </div>
                    <div className="bg-white/70 rounded-xl px-3 py-2 border border-gray-200">
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider flex items-center">
                        IC 95% (Paramétrico)
                        <InfoTooltip title="Intervalo de Confiança">
                          Faixa de valores onde a verdadeira diferença média provavelmente está, com 95% de confiança. Se o IC não inclui zero, há evidência de diferença real. O IC paramétrico assume distribuição normal; o bootstrap não faz essa suposição.
                        </InfoTooltip>
                      </p>
                      <p className="font-bold text-gray-800 font-mono text-sm">
                        [{ci?.lower ?? "?"}, {ci?.upper ?? "?"}]
                      </p>
                      <p className="text-[10px] text-gray-400">
                        Δ̄ = {ci?.mean_difference ?? "—"}
                      </p>
                    </div>
                    {bootstrapCI && bootstrapCI.method !== "insufficient_data" && (
                      <div className="bg-white/70 rounded-xl px-3 py-2 border border-gray-200">
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider flex items-center">
                          IC 95% (Bootstrap)
                          <InfoTooltip title="Bootstrap (Reamostragem)">
                            Método não-paramétrico que gera 10.000 amostras aleatórias com reposição para estimar o intervalo de confiança sem assumir normalidade. Mais robusto com amostras pequenas ou distribuições assimétricas.
                          </InfoTooltip>
                        </p>
                        <p className="font-bold text-gray-800 font-mono text-sm">
                          [{bootstrapCI.lower}, {bootstrapCI.upper}]
                        </p>
                        <p className="text-[10px] text-gray-400">
                          {bootstrapCI.n_bootstrap?.toLocaleString()} reamostras
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Normality info */}
              {normality && (
                <div className="px-6 py-2 bg-white/50 border-t border-gray-200 flex items-center gap-2 text-xs text-gray-500">
                  <Info className="w-3.5 h-3.5" />
                  Normalidade (Shapiro-Wilk)
                  <InfoTooltip title="Teste de Shapiro-Wilk">
                    Verifica se as diferenças pareadas seguem distribuição normal. Se p &gt; 0.05, assume-se normalidade e usa-se o t-test (mais poderoso). Caso contrário, usa-se o teste de Wilcoxon (não-paramétrico, livre de distribuição).
                  </InfoTooltip>
                  : W ={" "}
                  {normality.statistic ?? "—"}, p ={" "}
                  {formatP(normality.p_value)} →{" "}
                  {normality.is_normal
                    ? "Distribuição normal (teste paramétrico)"
                    : "Distribuição não normal (teste não-paramétrico)"}
                </div>
              )}
            </div>
          )}

          {/* =================== RANDOM BASELINE SECTION =================== */}
          {hasRandom && randomBaseline && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
                <Shuffle className="w-5 h-5 text-amber-500" />
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1">
                  Baseline Aleatório — Validação de Inteligência do Modelo
                  <InfoTooltip title="Baseline Aleatório">
                    Controle experimental essencial: testes adaptativos são selecionados aleatoriamente em vez de pelo modelo AutoML. Se AutoML &gt; Random, prova que a inteligência do modelo importa. Se Random &gt; Static, mostra que ter mais testes ajuda mesmo sem ML.
                  </InfoTooltip>
                </h3>
              </div>
              <div className="px-6 py-4">
                <p className="text-xs text-gray-500 mb-4">
                  O baseline aleatório seleciona testes adaptativos <strong>sem orientação do modelo</strong>.
                  Se AutoML &gt; Random, a inteligência do modelo importa — não apenas ter mais testes.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <ComparisonCard
                    title="AutoML vs. Random"
                    subtitle="Prova que a seleção inteligente supera a aleatória"
                    testResult={randomBaseline.automl_vs_random?.primary}
                    effectSize={randomBaseline.automl_vs_random?.effect_size}
                  />
                  <ComparisonCard
                    title="Random vs. Static"
                    subtitle="Sanidade: testes extras (mesmo aleatórios) ajudam?"
                    testResult={randomBaseline.random_vs_static?.primary}
                    effectSize={randomBaseline.random_vs_static?.effect_size}
                  />
                </div>
              </div>
            </div>
          )}

          {/* =================== POWER ANALYSIS (Phase 1C) =================== */}
          {powerAnalysis && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Gauge className="w-4 h-4" />
                Análise de Poder Estatístico (Post-Hoc)
                <InfoTooltip title="Poder Estatístico (1 - Beta)">
                  O poder é a probabilidade de detectar um efeito real quando ele existe. Poder &ge; 80% é considerado adequado. Se o poder é baixo, um resultado "não significativo" pode ser apenas falta de dados (erro Tipo II), não ausência de efeito. "N para 80%" indica quantos experimentos são necessários.
                </InfoTooltip>
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className={`rounded-xl px-4 py-3 border ${
                  powerAnalysis.observed_power >= 0.80
                    ? "bg-emerald-50 border-emerald-200"
                    : powerAnalysis.observed_power >= 0.60
                    ? "bg-amber-50 border-amber-200"
                    : "bg-red-50 border-red-200"
                }`}>
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Poder Observado</p>
                  <p className={`font-bold font-mono text-xl ${
                    powerAnalysis.observed_power >= 0.80
                      ? "text-emerald-700"
                      : powerAnalysis.observed_power >= 0.60
                      ? "text-amber-700"
                      : "text-red-700"
                  }`}>
                    {(powerAnalysis.observed_power * 100).toFixed(1)}%
                  </p>
                  <p className="text-[10px] text-gray-400">{powerAnalysis.interpretation}</p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">N Observado</p>
                  <p className="font-bold text-gray-800 font-mono text-lg">{powerAnalysis.observed_n}</p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">N p/ 80% Poder</p>
                  <p className="font-bold text-gray-800 font-mono text-lg">
                    {powerAnalysis.required_n_80 ?? "—"}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">N p/ 90% Poder</p>
                  <p className="font-bold text-gray-800 font-mono text-lg">
                    {powerAnalysis.required_n_90 ?? "—"}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Cohen's d</p>
                  <p className="font-bold text-gray-800 font-mono text-lg">
                    {powerAnalysis.observed_cohens_d}
                  </p>
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-3 italic">{powerAnalysis.note}</p>
            </div>
          )}

          {/* =================== PERMUTATION TEST (Phase 2A) =================== */}
          {permutationTest && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Shuffle className="w-4 h-4" />
                Teste de Permutação (Validação de Robustez)
                <InfoTooltip title="Teste de Permutação">
                  Método distribution-free que embaralha aleatoriamente os sinais das diferenças 10.000 vezes para construir uma distribuição nula empírica. Se o p-value concorda com o teste paramétrico, o resultado é robusto e não depende de suposições sobre a distribuição dos dados.
                </InfoTooltip>
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Teste</p>
                  <p className="font-semibold text-gray-800 text-xs">{permutationTest.test_name}</p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Diferença Média</p>
                  <p className="font-bold text-gray-800 font-mono">{permutationTest.observed_mean_diff}</p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">p-value</p>
                  <p className={`font-bold font-mono ${
                    permutationTest.reject_h0 ? "text-emerald-600" : "text-gray-800"
                  }`}>
                    {formatP(permutationTest.p_value)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {significanceBadge(permutationTest.reject_h0, permutationTest.p_value)}
                  <span className="text-xs text-gray-400">
                    ({permutationTest.n_permutations?.toLocaleString()} permutações)
                  </span>
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-3">
                Teste de permutação livre de distribuição que valida o resultado paramétrico.
                {permutationTest.reject_h0 === primary?.reject_h0
                  ? " ✓ Resultado consistente com o teste paramétrico."
                  : " ⚠ Resultado diverge do teste paramétrico — investigar."}
              </p>
            </div>
          )}

          {/* =================== LEVENE'S TEST (Phase 2C) =================== */}
          {varianceHomogeneity && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <BarChart3 className="w-4 h-4" />
                Homogeneidade de Variância (Levene)
                <InfoTooltip title="Teste de Levene">
                  Verifica se os três grupos (Static, AutoML, Random) têm variâncias similares — uma suposição de muitos testes paramétricos. Se p &gt; 0.05, as variâncias são consideradas homogêneas. Quando a suíte estática é determinística (variância ≈ 0), a heterogeneidade é esperada pelo design e não invalida os testes pareados.
                </InfoTooltip>
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Teste</p>
                  <p className="font-semibold text-gray-800 text-xs">{varianceHomogeneity.test_name}</p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Estatística</p>
                  <p className="font-bold text-gray-800 font-mono">{varianceHomogeneity.statistic}</p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">p-value</p>
                  <p className="font-bold text-gray-800 font-mono">{formatP(varianceHomogeneity.p_value)}</p>
                </div>
                <div className={`rounded-xl px-4 py-3 border ${
                  varianceHomogeneity.equal_variance
                    ? "bg-emerald-50 border-emerald-200"
                    : varianceHomogeneity.static_is_deterministic
                    ? "bg-blue-50 border-blue-200"
                    : "bg-amber-50 border-amber-200"
                }`}>
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">Resultado</p>
                  <p className={`font-semibold text-sm ${
                    varianceHomogeneity.equal_variance
                      ? "text-emerald-700"
                      : varianceHomogeneity.static_is_deterministic
                      ? "text-blue-700"
                      : "text-amber-700"
                  }`}>
                    {varianceHomogeneity.interpretation}
                  </p>
                </div>
              </div>

              {/* Group variances detail */}
              {varianceHomogeneity.group_variances && (
                <div className="grid grid-cols-3 gap-3 mt-3">
                  <div className="bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider">σ² Estática</p>
                    <p className="font-semibold text-gray-800 font-mono text-sm">{varianceHomogeneity.group_variances.static}</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider">σ² AutoML</p>
                    <p className="font-semibold text-gray-800 font-mono text-sm">{varianceHomogeneity.group_variances.automl}</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider">σ² Random</p>
                    <p className="font-semibold text-gray-800 font-mono text-sm">{varianceHomogeneity.group_variances.random}</p>
                  </div>
                </div>
              )}

              {/* Contextual explanation note */}
              {varianceHomogeneity.note && (
                <div className={`mt-3 p-3 rounded-lg border text-xs ${
                  varianceHomogeneity.static_is_deterministic
                    ? "bg-blue-50 border-blue-100 text-blue-700"
                    : varianceHomogeneity.equal_variance
                    ? "bg-emerald-50 border-emerald-100 text-emerald-700"
                    : "bg-amber-50 border-amber-100 text-amber-700"
                }`}>
                  {varianceHomogeneity.note}
                  {varianceHomogeneity.affects_primary_test === false && !varianceHomogeneity.equal_variance && (
                    <span className="font-semibold"> Não afeta o teste primário pareado.</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* =================== PAIRED OBSERVATIONS CHART =================== */}
          {pairChartData.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-violet-500" />
                <h3 className="text-sm font-semibold text-gray-700">
                  Vulnerabilidades Detectadas por Experimento
                </h3>
              </div>
              <div className="px-4 py-4" style={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={pairChartData}
                    margin={{ top: 10, right: 20, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 12,
                        border: "1px solid #e5e7eb",
                        fontSize: 12,
                      }}
                    />
                    <Legend
                      wrapperStyle={{ fontSize: 12 }}
                      iconType="circle"
                    />
                    <Bar
                      dataKey="static"
                      name="Estática"
                      fill="#3b82f6"
                      radius={[4, 4, 0, 0]}
                    />
                    {hasRandom && (
                      <Bar
                        dataKey="random"
                        name="Aleatório"
                        fill="#f59e0b"
                        radius={[4, 4, 0, 0]}
                      />
                    )}
                    <Bar
                      dataKey="automl"
                      name="AutoML"
                      fill="#8b5cf6"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Difference scatter */}
              <div className="px-6 py-3 border-t border-gray-100">
                <p className="text-xs text-gray-500 mb-2 font-medium">
                  Diferença por Experimento (AutoML − Estática)
                </p>
              </div>
              <div className="px-4 pb-4" style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis
                      dataKey="name"
                      type="category"
                      allowDuplicatedCategory={false}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis tick={{ fontSize: 11 }} />
                    <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 4" />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 12,
                        border: "1px solid #e5e7eb",
                        fontSize: 12,
                      }}
                      formatter={(val) => [`${val}`, "Diferença"]}
                    />
                    <Scatter data={pairChartData} dataKey="diff">
                      {pairChartData.map((entry, i) => (
                        <Cell
                          key={i}
                          fill={entry.diff > 0 ? "#10b981" : entry.diff < 0 ? "#ef4444" : "#9ca3af"}
                          r={6}
                        />
                      ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* =================== PER-PROTOCOL BREAKDOWN =================== */}
          {perProtocol.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
                <Shield className="w-5 h-5 text-blue-500" />
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1">
                  Taxa de Detecção por Protocolo (Fisher's Exact Test)
                  <InfoTooltip title="Fisher's Exact Test">
                    Teste exato para tabelas de contingência 2x2 (vulnerável vs. não-vulnerável &times; estática vs. AutoML) por protocolo. Ideal para amostras pequenas pois calcula a probabilidade exata sem aproximações. Os p-values são corrigidos por Holm-Bonferroni para múltiplas comparações.
                  </InfoTooltip>
                </h3>
              </div>

              {/* Chart */}
              {protoChartData.length > 0 && (
                <div className="px-4 py-4" style={{ height: 280 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={protoChartData}
                      margin={{ top: 10, right: 20, left: 0, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="protocol" tick={{ fontSize: 11 }} />
                      <YAxis
                        tick={{ fontSize: 11 }}
                        unit="%"
                        domain={[0, 100]}
                      />
                      <Tooltip
                        contentStyle={{
                          borderRadius: 12,
                          border: "1px solid #e5e7eb",
                          fontSize: 12,
                        }}
                        formatter={(val) => [`${val}%`, ""]}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
                      <Bar
                        dataKey="static_rate"
                        name="Estática"
                        fill="#3b82f6"
                        radius={[4, 4, 0, 0]}
                      />
                      {hasRandom && (
                        <Bar
                          dataKey="random_rate"
                          name="Aleatório"
                          fill="#f59e0b"
                          radius={[4, 4, 0, 0]}
                        />
                      )}
                      <Bar
                        dataKey="automl_rate"
                        name="AutoML"
                        fill="#8b5cf6"
                        radius={[4, 4, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Table */}
              <div className="px-6 pb-4">
                {multipleComparison && (
                  <div className="mb-3 p-3 bg-blue-50 rounded-lg border border-blue-100 text-xs text-blue-700">
                    <strong>Correção para comparações múltiplas:</strong>{" "}
                    {multipleComparison.n_comparisons} comparações — método recomendado:{" "}
                    <strong>{multipleComparison.recommended}</strong>.{" "}
                    <span className="text-blue-500">{multipleComparison.note}</span>
                  </div>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-gray-200">
                        <th className="py-2 pr-3">Protocolo</th>
                        <th className="py-2 px-3">Estática</th>
                        {hasRandom && <th className="py-2 px-3">Aleatório</th>}
                        <th className="py-2 px-3">AutoML</th>
                        <th className="py-2 px-3">Fisher p</th>
                        <th className="py-2 px-3">
                          <span className="flex items-center">
                            p (Holm)
                            <InfoTooltip title="Correção de Holm-Bonferroni">
                              Ao testar múltiplos protocolos simultaneamente, a chance de falsos positivos aumenta. A correção de Holm ajusta os p-values para controlar o erro familywise (FWER), sendo mais poderosa que a correção de Bonferroni simples.
                            </InfoTooltip>
                          </span>
                        </th>
                        <th className="py-2 px-3">
                          <span className="flex items-center">
                            Cramér's V
                            <InfoTooltip title="Cramér's V (Tamanho do Efeito)">
                              Mede a força de associação em tabelas de contingência, análogo ao Cohen's d para dados categóricos. V &lt; 0.1 = negligenciável, 0.1-0.3 = pequeno, 0.3-0.5 = médio, &ge; 0.5 = grande. Complementa o p-value com informação sobre magnitude prática.
                            </InfoTooltip>
                          </span>
                        </th>
                        <th className="py-2 pl-3">Resultado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {perProtocol.map((p) => (
                        <tr
                          key={p.protocol}
                          className="border-b border-gray-50 last:border-0"
                        >
                          <td className="py-2 pr-3 font-mono font-semibold text-gray-700 uppercase">
                            {p.protocol}
                          </td>
                          <td className="py-2 px-3 text-gray-600">
                            {p.static_vulns}/{p.static_tests}{" "}
                            <span className="text-gray-400">
                              ({(p.static_rate * 100).toFixed(1)}%)
                            </span>
                          </td>
                          {hasRandom && (
                            <td className="py-2 px-3 text-gray-600">
                              {p.random_vulns !== undefined && p.random_vulns !== null ? (
                                <>
                                  {p.random_vulns}/{p.random_tests}{" "}
                                  <span className="text-gray-400">
                                    ({(p.random_rate * 100).toFixed(1)}%)
                                  </span>
                                </>
                              ) : (
                                <span className="text-gray-400">—</span>
                              )}
                            </td>
                          )}
                          <td className="py-2 px-3 text-gray-600">
                            {p.automl_vulns}/{p.automl_tests}{" "}
                            <span className="text-gray-400">
                              ({(p.automl_rate * 100).toFixed(1)}%)
                            </span>
                          </td>
                          <td className="py-2 px-3 font-mono text-xs text-gray-400">
                            {formatP(p.fisher_p)}
                          </td>
                          <td className="py-2 px-3 font-mono text-xs">
                            {p.fisher_p_holm !== undefined ? (
                              <span className={p.significant_holm ? "text-emerald-600 font-semibold" : ""}>
                                {formatP(p.fisher_p_holm)}
                              </span>
                            ) : (
                              formatP(p.fisher_p)
                            )}
                          </td>
                          <td className="py-2 px-3 font-mono text-xs">
                            {p.cramers_v !== undefined ? (
                              <span title={p.cramers_v_interpretation}>
                                {p.cramers_v.toFixed(3)}{" "}
                                <span className="text-gray-400 text-[10px]">
                                  ({p.cramers_v_interpretation})
                                </span>
                              </span>
                            ) : "—"}
                          </td>
                          <td className="py-2 pl-3">
                            {p.significant_holm !== undefined
                              ? significanceBadge(p.significant_holm, p.fisher_p_holm)
                              : significanceBadge(p.significant, p.fisher_p)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* =================== INDEPENDENT TEST =================== */}
          {independent && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <BarChart3 className="w-4 h-4" />
                Comparação Independente
                <InfoTooltip title="Mann-Whitney U">
                  Teste não-paramétrico para amostras independentes (não-pareadas). Usado quando há experimentos executados apenas com suíte estática, sem contraparte AutoML. Complementa o teste pareado com dados adicionais de experimentos independentes.
                </InfoTooltip>
              </h3>
              <div className="flex flex-wrap items-center gap-4">
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                    Teste
                  </p>
                  <p className="font-semibold text-gray-800 text-sm">
                    {independent.test_name}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                    N AutoML / N Static
                  </p>
                  <p className="font-semibold text-gray-800 font-mono">
                    {independent.automl_n} / {independent.static_only_n}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                    U
                  </p>
                  <p className="font-semibold text-gray-800 font-mono">
                    {independent.statistic}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                    p-value
                  </p>
                  <p
                    className={`font-semibold font-mono ${
                      independent.reject_h0
                        ? "text-emerald-600"
                        : "text-gray-800"
                    }`}
                  >
                    {formatP(independent.p_value)}
                  </p>
                </div>
                <div>{significanceBadge(independent.reject_h0, independent.p_value)}</div>
              </div>
            </div>
          )}

          {/* =================== EXECUTION TIME =================== */}
          {execTime && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Timer className="w-4 h-4" />
                Comparação de Tempo de Execução
                <InfoTooltip title="Tempo de Execução">
                  Analisa se a estratégia AutoML é significativamente mais lenta que a estática. Um tempo maior é esperado (mais testes), mas deve ser proporcional ao ganho em detecção. Usa teste pareado bilateral — qualquer diferença significativa é reportada.
                </InfoTooltip>
              </h3>
              <div className={`grid grid-cols-2 ${hasRandom ? "md:grid-cols-6" : "md:grid-cols-5"} gap-3`}>
                <div className="bg-blue-50 rounded-xl px-4 py-3 border border-blue-100">
                  <p className="text-[10px] text-blue-500 uppercase tracking-wider">
                    Estática (média)
                  </p>
                  <p className="font-bold text-blue-700 font-mono">
                    {execTime.static_mean_sec}s
                  </p>
                </div>
                {hasRandom && execTime.random_mean_sec !== undefined && execTime.random_mean_sec !== null && (
                  <div className="bg-amber-50 rounded-xl px-4 py-3 border border-amber-100">
                    <p className="text-[10px] text-amber-500 uppercase tracking-wider">
                      Aleatório (média)
                    </p>
                    <p className="font-bold text-amber-700 font-mono">
                      {execTime.random_mean_sec}s
                    </p>
                  </div>
                )}
                <div className="bg-violet-50 rounded-xl px-4 py-3 border border-violet-100">
                  <p className="text-[10px] text-violet-500 uppercase tracking-wider">
                    AutoML (média)
                  </p>
                  <p className="font-bold text-violet-700 font-mono">
                    {execTime.automl_mean_sec}s
                  </p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                    Teste
                  </p>
                  <p className="font-semibold text-gray-800 text-xs">
                    {execTime.test_name}
                  </p>
                </div>
                <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                    p-value
                  </p>
                  <p
                    className={`font-bold font-mono ${
                      execTime.significant
                        ? "text-amber-600"
                        : "text-gray-800"
                    }`}
                  >
                    {formatP(execTime.p_value)}
                  </p>
                </div>
                <div className="flex items-center">
                  {significanceBadge(execTime.significant, execTime.p_value)}
                </div>
              </div>
            </div>
          )}

          {/* =================== EFFICIENCY METRIC =================== */}
          {efficiency && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Gauge className="w-4 h-4" />
                Eficiência de Detecção (Vulns / Teste)
                <InfoTooltip title="Eficiência de Detecção">
                  Razão entre vulnerabilidades encontradas e total de testes executados. A eficiência global mede o aproveitamento geral. A eficiência marginal mede apenas o retorno dos testes extras que o AutoML seleciona além da suíte estática — o indicador mais relevante da qualidade da seleção adaptativa.
                </InfoTooltip>
              </h3>

              {/* Overall Efficiency Row */}
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Eficiência Global</p>
              <div className={`grid grid-cols-2 ${hasRandom && efficiency.random ? "md:grid-cols-5" : "md:grid-cols-4"} gap-3`}>
                <div className="bg-blue-50 rounded-xl px-4 py-3 border border-blue-100">
                  <p className="text-[10px] text-blue-500 uppercase tracking-wider">Estática</p>
                  <p className="font-bold text-blue-700 font-mono text-lg">
                    {(efficiency.static?.mean * 100).toFixed(1)}%
                  </p>
                  <p className="text-[10px] text-blue-400">
                    ± {(efficiency.static?.std * 100).toFixed(1)}%
                  </p>
                </div>
                {hasRandom && efficiency.random && (
                  <div className="bg-amber-50 rounded-xl px-4 py-3 border border-amber-100">
                    <p className="text-[10px] text-amber-500 uppercase tracking-wider">Aleatório</p>
                    <p className="font-bold text-amber-700 font-mono text-lg">
                      {(efficiency.random.mean * 100).toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-amber-400">
                      ± {(efficiency.random.std * 100).toFixed(1)}%
                    </p>
                  </div>
                )}
                <div className="bg-violet-50 rounded-xl px-4 py-3 border border-violet-100">
                  <p className="text-[10px] text-violet-500 uppercase tracking-wider">AutoML</p>
                  <p className="font-bold text-violet-700 font-mono text-lg">
                    {(efficiency.automl?.mean * 100).toFixed(1)}%
                  </p>
                  <p className="text-[10px] text-violet-400">
                    ± {(efficiency.automl?.std * 100).toFixed(1)}%
                  </p>
                </div>
                <div className={`rounded-xl px-4 py-3 border ${
                  efficiency.automl_improvement_pct > 0
                    ? "bg-emerald-50 border-emerald-100"
                    : "bg-gray-50 border-gray-200"
                }`}>
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                    Δ Global
                  </p>
                  <p className={`font-bold font-mono text-lg ${
                    efficiency.automl_improvement_pct > 0
                      ? "text-emerald-700"
                      : "text-gray-600"
                  }`}>
                    {efficiency.automl_improvement_pct > 0 ? "+" : ""}
                    {efficiency.automl_improvement_pct}%
                  </p>
                  <p className="text-[10px] text-gray-400">vs. estática</p>
                </div>
                {efficiency.test && (
                  <div className="flex items-center">
                    {significanceBadge(efficiency.test.reject_h0, efficiency.test.p_value)}
                  </div>
                )}
              </div>
              {efficiency.test && (
                <p className="text-xs text-gray-500 mt-2">
                  {efficiency.test.test_name}: p = {formatP(efficiency.test.p_value)}
                  {efficiency.effect_size && (
                    <span>, d = {efficiency.effect_size.cohens_d} ({efficiency.effect_size.interpretation})</span>
                  )}
                </p>
              )}

              {/* Explanation note for global efficiency */}
              {efficiency.automl_improvement_pct <= 0 && (
                <div className="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-100 text-xs text-blue-700">
                  <strong>Nota:</strong> A eficiência global do AutoML é menor porque inclui testes exploratórios
                  em território incerto. A métrica relevante é a <strong>eficiência marginal</strong> abaixo,
                  que mede o retorno dos testes adicionais selecionados pelo modelo.
                </div>
              )}

              {/* Marginal Efficiency Row */}
              {efficiency.marginal && (
                <>
                  <div className="border-t border-gray-100 mt-5 pt-4">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                      Eficiência Marginal (Testes Adicionais do AutoML)
                      <InfoTooltip title="Eficiência Marginal">
                        Mede apenas o retorno dos testes extras que o AutoML seleciona além da suíte estática fixa.
                        Responde à pergunta: "Para cada teste adicional que o modelo decide executar, qual a probabilidade
                        de encontrar uma nova vulnerabilidade?" Se a eficiência marginal é positiva, os testes extras
                        são produtivos — o modelo está selecionando testes relevantes, não aleatórios.
                      </InfoTooltip>
                    </p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="bg-violet-50 rounded-xl px-4 py-3 border border-violet-200">
                        <p className="text-[10px] text-violet-500 uppercase tracking-wider">Efic. Marginal</p>
                        <p className="font-bold text-violet-700 font-mono text-lg">
                          {(efficiency.marginal.mean * 100).toFixed(1)}%
                        </p>
                        <p className="text-[10px] text-violet-400">
                          ± {(efficiency.marginal.std * 100).toFixed(1)}%
                        </p>
                      </div>
                      <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider">Vulns Extras (média)</p>
                        <p className="font-bold text-gray-800 font-mono text-lg">
                          +{efficiency.marginal.extra_vulns_mean}
                        </p>
                        <p className="text-[10px] text-gray-400">por experimento</p>
                      </div>
                      <div className="bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider">Testes Extras (média)</p>
                        <p className="font-bold text-gray-800 font-mono text-lg">
                          +{efficiency.marginal.extra_tests_mean}
                        </p>
                        <p className="text-[10px] text-gray-400">por experimento</p>
                      </div>
                      {efficiency.marginal.test && (
                        <div className="flex items-center justify-center">
                          {significanceBadge(efficiency.marginal.test.reject_h0, efficiency.marginal.test.p_value)}
                        </div>
                      )}
                    </div>
                    {efficiency.marginal.test && (
                      <p className="text-xs text-gray-500 mt-2">
                        {efficiency.marginal.test.test_name}: p = {formatP(efficiency.marginal.test.p_value)}
                      </p>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {/* =================== LEARNING CURVE =================== */}
          {learningCurve.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
                <GraduationCap className="w-5 h-5 text-violet-500" />
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1">
                  Curva de Aprendizagem — Convergência Estatística
                  <InfoTooltip title="Curva de Convergência">
                    Mostra como as métricas estatísticas evoluem à medida que mais experimentos são adicionados. O p-value deve convergir (estabilizar) com N suficiente. Se ainda oscila, mais experimentos são necessários para conclusões robustas. A estabilidade é verificada nos últimos 5 pontos.
                  </InfoTooltip>
                </h3>
              </div>
              <div className="px-4 py-4" style={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={learningCurve}
                    margin={{ top: 10, right: 20, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis
                      dataKey="n"
                      tick={{ fontSize: 11 }}
                      label={{ value: "N experimentos", position: "insideBottom", offset: -2, fontSize: 11 }}
                    />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ borderRadius: 12, border: "1px solid #e5e7eb", fontSize: 12 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
                    <Line
                      dataKey="automl_mean"
                      name="AutoML (média)"
                      stroke="#8b5cf6"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                    />
                    <Line
                      dataKey="static_mean"
                      name="Estática (média)"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                    />
                    {learningCurve.some((p) => p.random_mean !== undefined) && (
                      <Line
                        dataKey="random_mean"
                        name="Aleatório (média)"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        dot={{ r: 2 }}
                      />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* P-value convergence */}
              <div className="px-6 py-3 border-t border-gray-100">
                <p className="text-xs text-gray-500 mb-2 font-medium">
                  Convergência do p-value (linha tracejada = α = 0.05)
                </p>
              </div>
              <div className="px-4 pb-4" style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={learningCurve}
                    margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="n" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} domain={[0, 1]} />
                    <Tooltip
                      contentStyle={{ borderRadius: 12, border: "1px solid #e5e7eb", fontSize: 12 }}
                      formatter={(val) => [val?.toFixed(6), ""]}
                    />
                    <ReferenceLine y={0.05} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "α=0.05", fontSize: 10, fill: "#ef4444" }} />
                    <Line
                      dataKey="p_value"
                      name="p-value"
                      stroke="#10b981"
                      strokeWidth={2}
                      dot={(props) => {
                        const { cx, cy, payload } = props;
                        return (
                          <circle
                            cx={cx}
                            cy={cy}
                            r={4}
                            fill={payload.significant ? "#10b981" : "#9ca3af"}
                            stroke="white"
                            strokeWidth={1}
                          />
                        );
                      }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Convergence stability indicator */}
              {lcStability && (
                <div className="px-6 py-3 border-t border-gray-100">
                  <div className={`flex items-center gap-3 p-3 rounded-lg border ${
                    lcStability.converged
                      ? "bg-emerald-50 border-emerald-200"
                      : "bg-amber-50 border-amber-200"
                  }`}>
                    {lcStability.converged ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                    ) : (
                      <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
                    )}
                    <div className="flex-1">
                      <p className={`text-sm font-semibold ${
                        lcStability.converged ? "text-emerald-700" : "text-amber-700"
                      }`}>
                        {lcStability.converged
                          ? "Resultado convergiu — p-values estáveis"
                          : "Resultado ainda não convergiu"}
                      </p>
                      <div className="flex flex-wrap gap-4 mt-1 text-xs text-gray-500">
                        <span>
                          Range últimos 5 p-values:{" "}
                          <span className="font-mono font-semibold">
                            {lcStability.p_value_range?.toFixed(6) ?? "—"}
                          </span>
                        </span>
                        <span>
                          Direção consistente:{" "}
                          <span className="font-semibold">
                            {lcStability.direction_consistent ? "Sim ✓" : "Não ✗"}
                          </span>
                        </span>
                        {lcStability.minimum_n_for_stability && (
                          <span>
                            N mín. p/ estabilidade:{" "}
                            <span className="font-mono font-semibold">
                              {lcStability.minimum_n_for_stability}
                            </span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* =================== ROC CURVE & MODEL METRICS =================== */}
          {modelMetrics?.aggregate?.latest_roc_curve && (
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider flex items-center gap-2 mb-2">
                <TrendingUp className="w-4 h-4" />
                Desempenho do Modelo AutoML
                <InfoTooltip title="Curva ROC e Métricas CV">
                  A curva ROC (Receiver Operating Characteristic) mostra a capacidade discriminativa do modelo: TPR (sensibilidade) vs. FPR (1-especificidade). AUC = 1.0 é perfeito, 0.5 é aleatório. Precision mede acertos positivos, Recall mede cobertura de positivos, e F1 é a média harmônica de ambos. Métricas são de cross-validation (5-fold).
                </InfoTooltip>
              </h3>
              <RocCurveChart
                rocData={modelMetrics.aggregate.latest_roc_curve}
                cvMetrics={modelMetrics.aggregate.cv_classification_metrics}
              />
            </div>
          )}

          {/* =================== CONCLUSION =================== */}
          {conclusion && (
            <div
              className={`rounded-2xl border-2 p-6 ${
                primary?.reject_h0
                  ? "border-emerald-300 bg-emerald-50"
                  : "border-gray-300 bg-gray-50"
              }`}
            >
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                <BookOpen className="w-4 h-4" />
                Conclusão
              </h3>
              <p className="text-gray-700 leading-relaxed">
                {conclusion.text_pt}
              </p>
              <p className="text-gray-500 text-sm mt-3 italic leading-relaxed">
                {conclusion.text_en}
              </p>
            </div>
          )}

          {/* =================== RAW DATA TOGGLE =================== */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <button
              onClick={() => setShowRawPairs(!showRawPairs)}
              className="w-full px-6 py-3 flex items-center justify-between text-sm font-medium text-gray-600 hover:bg-gray-50 transition"
            >
              <span>Dados Brutos ({rawPairs.length} pares)</span>
              {showRawPairs ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
            {showRawPairs && rawPairs.length > 0 && (
              <div className="px-6 pb-4 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-500 uppercase tracking-wider border-b border-gray-200">
                      <th className="py-2 pr-2">#</th>
                      <th className="py-2 px-2">Experimento</th>
                      <th className="py-2 px-2 text-right">Vulns Static</th>
                      {hasRandom && (
                        <th className="py-2 px-2 text-right">Vulns Random</th>
                      )}
                      <th className="py-2 px-2 text-right">Vulns AutoML</th>
                      <th className="py-2 px-2 text-right">Δ (A−S)</th>
                      <th className="py-2 px-2 text-right">Testes Static</th>
                      {hasRandom && (
                        <th className="py-2 px-2 text-right">Testes Random</th>
                      )}
                      <th className="py-2 px-2 text-right">Testes AutoML</th>
                      <th className="py-2 px-2 text-right">Tempo Static</th>
                      {hasRandom && (
                        <th className="py-2 px-2 text-right">Tempo Random</th>
                      )}
                      <th className="py-2 pl-2 text-right">Tempo AutoML</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rawPairs.map((p, i) => (
                      <tr
                        key={p.experiment}
                        className="border-b border-gray-50 last:border-0 hover:bg-gray-50"
                      >
                        <td className="py-1.5 pr-2 text-gray-400">{i + 1}</td>
                        <td className="py-1.5 px-2 font-mono text-gray-600">
                          {p.experiment}
                        </td>
                        <td className="py-1.5 px-2 text-right font-mono text-blue-600">
                          {p.static_vulns}
                        </td>
                        {hasRandom && (
                          <td className="py-1.5 px-2 text-right font-mono text-amber-600">
                            {p.random_vulns ?? "—"}
                          </td>
                        )}
                        <td className="py-1.5 px-2 text-right font-mono text-violet-600">
                          {p.automl_vulns}
                        </td>
                        <td
                          className={`py-1.5 px-2 text-right font-mono font-bold ${
                            p.automl_vulns - p.static_vulns > 0
                              ? "text-emerald-600"
                              : p.automl_vulns - p.static_vulns < 0
                              ? "text-red-500"
                              : "text-gray-400"
                          }`}
                        >
                          {p.automl_vulns - p.static_vulns > 0 ? "+" : ""}
                          {p.automl_vulns - p.static_vulns}
                        </td>
                        <td className="py-1.5 px-2 text-right text-gray-500">
                          {p.static_tests}
                        </td>
                        {hasRandom && (
                          <td className="py-1.5 px-2 text-right text-gray-500">
                            {p.random_tests ?? "—"}
                          </td>
                        )}
                        <td className="py-1.5 px-2 text-right text-gray-500">
                          {p.automl_tests}
                        </td>
                        <td className="py-1.5 px-2 text-right text-gray-500">
                          {p.static_time.toFixed(1)}s
                        </td>
                        {hasRandom && (
                          <td className="py-1.5 px-2 text-right text-gray-500">
                            {p.random_time !== undefined && p.random_time !== null
                              ? p.random_time.toFixed(1) + "s"
                              : "—"}
                          </td>
                        )}
                        <td className="py-1.5 pl-2 text-right text-gray-500">
                          {p.automl_time.toFixed(1)}s
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
