import { useState } from "react";
import ExperimentRunner from "./ExperimentRunner";
import RealTimeLogs from "./RealTimeLogs";

export default function Dashboard({ metrics, apiUrl, refreshAll, onNavigateToStats }) {
  const [lastExperimentId, setLastExperimentId] = useState(null);

  return (
    <div className="space-y-8">
      {/* Experiment Configuration & Runner */}
      <ExperimentRunner
        onExperimentComplete={(expId) => {
          setLastExperimentId(expId);
          refreshAll();
        }}
        refreshAll={refreshAll}
        onNavigateToStats={onNavigateToStats}
      />

      {/* Real-Time Logs */}
      <div className="max-w-6xl mx-auto">
        <RealTimeLogs apiUrl={apiUrl} />
      </div>
    </div>
  );
}
