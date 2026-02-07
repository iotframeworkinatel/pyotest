import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, Legend, ResponsiveContainer, Tooltip,
} from "recharts";
import { Card, CardHeader, CardContent } from "../ui/card";
import { STRATEGY_COLORS } from "../../utils/chartColors";

export default function StrategyComparisonChart({ data }) {
  if (!data || data.length < 2) return null;

  const staticD = data.find((d) => d.test_strategy === "static") || {};
  const automlD = data.find((d) => d.test_strategy === "automl") || {};

  const dims = [
    { key: "total_tests", label: "Total Testes" },
    { key: "vulns_found", label: "Vulns Detectadas" },
    { key: "detection_rate", label: "Taxa Detecção (%)" },
    { key: "unique_devices", label: "Dispositivos" },
    { key: "unique_protocols", label: "Protocolos" },
    { key: "efficiency", label: "Eficiência" },
  ];

  const maxValues = {};
  dims.forEach(({ key }) => {
    maxValues[key] = Math.max(staticD[key] || 0, automlD[key] || 0, 1);
  });

  const radarData = dims.map(({ key, label }) => ({
    dimension: label,
    static: Math.round(((staticD[key] || 0) / maxValues[key]) * 100),
    automl: Math.round(((automlD[key] || 0) / maxValues[key]) * 100),
  }));

  return (
    <Card>
      <CardHeader>Comparação Static vs AutoML</CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={350}>
          <RadarChart data={radarData}>
            <PolarGrid />
            <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11 }} />
            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
            <Radar
              name="Static"
              dataKey="static"
              stroke={STRATEGY_COLORS.static}
              fill={STRATEGY_COLORS.static}
              fillOpacity={0.3}
            />
            <Radar
              name="AutoML"
              dataKey="automl"
              stroke={STRATEGY_COLORS.automl}
              fill={STRATEGY_COLORS.automl}
              fillOpacity={0.3}
            />
            <Legend />
            <Tooltip />
          </RadarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
