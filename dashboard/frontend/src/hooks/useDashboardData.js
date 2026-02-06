import { useEffect, useState, useRef } from "react";
import { fetchExperiments, fetchMetrics, fetchLogs, fetchHistory } from "../api/experiments";

export function useDashboardData() {
  const [experiments, setExperiments] = useState([]);
  const [metrics, setMetrics] = useState([]);
  const [history, setHistory] = useState([]);
  const [logs, setLogs] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const logRef = useRef(null);
  let logIntervalRef = useRef(null);

  async function refreshAll() {
    try {
      const [exps, mets, logs, hist] = await Promise.all([
        fetchExperiments(),
        fetchMetrics(),
        fetchLogs(),
        fetchHistory(),
      ]);
      setExperiments(exps.experiments || []);
      setMetrics(mets.metrics || []);
      setLogs(logs.logs || "Sem logs");
      setHistory(hist.history || []);
    } catch (err) {
      console.error("Erro ao atualizar:", err);
    }
  }

  const startLogStreaming = () => {
    if (isStreaming) return;
    setIsStreaming(true);
    logIntervalRef.current = setInterval(async () => {
      try {
        const data = await fetchLogs();
        setLogs(data.logs || "Sem logs...");
        if (logRef.current)
          logRef.current.scrollTop = logRef.current.scrollHeight;
      } catch (err) {
        setLogs("Erro ao obter logs: " + err.message);
      }
    }, 2000);
  };

  const stopLogStreaming = () => {
    setIsStreaming(false);
    clearInterval(logIntervalRef.current);
  };

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 15000);
    return () => clearInterval(interval);
  }, []);

  return {
    experiments,
    metrics,
    history,
    logs,
    logRef,
    isStreaming,
    startLogStreaming,
    stopLogStreaming,
    refreshAll,
  };
}
