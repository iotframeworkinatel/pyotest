import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Card, CardHeader, CardContent } from "../ui/card";
import { STRATEGY_COLORS } from "../../utils/chartColors";

export default function CumulativeVulnsChart({ data }) {
  if (!data || data.length === 0) return null;

  const strategies = [...new Set(data.map((d) => d.test_strategy))];
  const maxIndex = Math.max(...data.map((d) => d.test_index));

  const merged = [];
  for (let i = 1; i <= maxIndex; i++) {
    const point = { test_index: i };
    strategies.forEach((s) => {
      const match = data.find((d) => d.test_strategy === s && d.test_index === i);
      point[s] = match ? match.cumulative_vulns : null;
    });
    merged.push(point);
  }

  return (
    <Card>
      <CardHeader>Descoberta Cumulativa de Vulnerabilidades</CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={merged}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="test_index"
              label={{ value: "Ordem de Execução", position: "insideBottom", offset: -5 }}
            />
            <YAxis
              label={{ value: "Vulns Cumulativas", angle: -90, position: "insideLeft" }}
            />
            <Tooltip />
            <Legend />
            {strategies.map((s) => (
              <Line
                key={s}
                type="monotone"
                dataKey={s}
                name={s === "automl" ? "AutoML" : "Static"}
                stroke={STRATEGY_COLORS[s] || "#8884d8"}
                strokeWidth={2}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
