import { useEffect, useState } from "react";
import { fetchExperiments, fetchHistory } from "../api/experiments";

export function useDashboardData() {
  const [experiments, setExperiments] = useState([]);
  const [history, setHistory] = useState([]);

  async function refreshAll() {
    try {
      const [exps, mets, hist] = await Promise.all([
        fetchExperiments(),
        fetchHistory(),
      ]);
      setExperiments(exps.experiments || []);
      setHistory(hist.history || []);
    } catch (err) {
      console.error("Erro ao atualizar:", err);
    }
  }

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, 15000);
    return () => clearInterval(interval);
  }, []);

  return {
    experiments,
    history,
    refreshAll,
  };
}
