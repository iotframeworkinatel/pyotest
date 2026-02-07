import { useState } from "react";
import { useHistoryData } from "../hooks/useHistoryData";
import KpiCards from "./charts/KpiCards";
import ExperimentSelector from "./charts/ExperimentSelector";
import VulnsByProtocolChart from "./charts/VulnsByProtocolChart";
import VulnsByTypeChart from "./charts/VulnsByTypeChart";
import CumulativeVulnsChart from "./charts/CumulativeVulnsChart";
import ExecTimeDistChart from "./charts/ExecTimeDistChart";
import DeviceVulnsChart from "./charts/DeviceVulnsChart";
import StrategyComparisonChart from "./charts/StrategyComparisonChart";
import AutomlScoresChart from "./charts/AutomlScoresChart";

export default function History() {
  const [selectedExperiment, setSelectedExperiment] = useState(null);

  const {
    experiments,
    summary,
    vulnsByProtocol,
    vulnsByType,
    vulnsByDevice,
    execTimeDist,
    cumulativeVulns,
    strategyComparison,
    automlScores,
    loading,
    refresh,
  } = useHistoryData(selectedExperiment);

  return (
    <div className="max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold mb-4 text-center">
        Histórico de Experimentos
      </h2>

      <ExperimentSelector
        experiments={experiments}
        selected={selectedExperiment}
        onSelect={setSelectedExperiment}
        onRefresh={refresh}
        loading={loading}
      />

      {loading ? (
        <div className="text-center py-12 text-gray-500">
          Carregando dados...
        </div>
      ) : (
        <>
          <KpiCards summary={summary} />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <StrategyComparisonChart data={strategyComparison} />
            <CumulativeVulnsChart data={cumulativeVulns} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <VulnsByProtocolChart data={vulnsByProtocol} />
            <VulnsByTypeChart data={vulnsByType} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <ExecTimeDistChart data={execTimeDist} />
            <DeviceVulnsChart data={vulnsByDevice} />
          </div>

          <div className="mb-6">
            <AutomlScoresChart data={automlScores} />
          </div>
        </>
      )}
    </div>
  );
}
