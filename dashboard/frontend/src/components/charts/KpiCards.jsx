import { Card, CardContent } from "../ui/card";
import { Shield, Bug, Cpu, Clock, Activity, Wifi } from "lucide-react";

const KPI_DEFS = [
  { key: "total_experiments", label: "Experimentos", icon: Activity, color: "text-blue-500" },
  { key: "total_tests", label: "Testes Executados", icon: Cpu, color: "text-green-500" },
  { key: "total_vulns", label: "Vulnerabilidades", icon: Bug, color: "text-red-500" },
  { key: "total_devices", label: "Dispositivos", icon: Wifi, color: "text-purple-500" },
  { key: "detection_rate", label: "Taxa Detecção (%)", icon: Shield, color: "text-orange-500" },
  { key: "avg_exec_time_ms", label: "Tempo Médio (ms)", icon: Clock, color: "text-cyan-500" },
];

export default function KpiCards({ summary }) {
  if (!summary || Object.keys(summary).length === 0) return null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
      {KPI_DEFS.map(({ key, label, icon: Icon, color }) => (
        <Card key={key}>
          <CardContent className="flex flex-col items-center py-4">
            <Icon className={`w-8 h-8 mb-2 ${color}`} />
            <span className="text-2xl font-bold">{summary[key] ?? "—"}</span>
            <span className="text-xs text-gray-500 mt-1 text-center">{label}</span>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
