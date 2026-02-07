import { useEffect, useState, useCallback } from "react";
import {
  fetchExperiments,
  fetchHistorySummary,
  fetchVulnsByProtocol,
  fetchVulnsByType,
  fetchVulnsByDevice,
  fetchExecTimeDistribution,
  fetchCumulativeVulns,
  fetchStrategyComparison,
  fetchAutomlScores,
} from "../api/experiments";

export function useHistoryData(selectedExperiment = null) {
  const [experiments, setExperiments] = useState([]);
  const [summary, setSummary] = useState({});
  const [vulnsByProtocol, setVulnsByProtocol] = useState([]);
  const [vulnsByType, setVulnsByType] = useState([]);
  const [vulnsByDevice, setVulnsByDevice] = useState([]);
  const [execTimeDist, setExecTimeDist] = useState([]);
  const [cumulativeVulns, setCumulativeVulns] = useState([]);
  const [strategyComparison, setStrategyComparison] = useState([]);
  const [automlScores, setAutomlScores] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const exp = selectedExperiment || null;
      const [exps, sum, proto, type_, device, exec_, cumul, strat, aml] =
        await Promise.all([
          fetchExperiments(),
          fetchHistorySummary(exp),
          fetchVulnsByProtocol(exp),
          fetchVulnsByType(exp),
          fetchVulnsByDevice(exp),
          fetchExecTimeDistribution(exp),
          fetchCumulativeVulns(exp),
          fetchStrategyComparison(exp),
          fetchAutomlScores(exp),
        ]);

      setExperiments(exps.experiments || []);
      setSummary(sum.summary || {});
      setVulnsByProtocol(proto.data || []);
      setVulnsByType(type_.data || []);
      setVulnsByDevice(device.data || []);
      setExecTimeDist(exec_.data || []);
      setCumulativeVulns(cumul.data || []);
      setStrategyComparison(strat.data || []);
      setAutomlScores(aml.data || []);
    } catch (err) {
      console.error("Erro ao carregar dados do historico:", err);
    } finally {
      setLoading(false);
    }
  }, [selectedExperiment]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return {
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
  };
}
