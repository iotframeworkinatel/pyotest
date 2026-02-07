import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";
import { Card, CardHeader, CardContent } from "../ui/card";
import { PROTOCOL_COLORS } from "../../utils/chartColors";

export default function AutomlScoresChart({ data }) {
  if (!data || data.length === 0) return null;

  const top20 = data.slice(0, 20).map((d) => ({
    label: `${d.protocol}:${d.test_id}`,
    risk_score: d.risk_score,
    protocol: d.protocol,
  }));

  return (
    <Card>
      <CardHeader>Top 20 Testes AutoML (Risk Score)</CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={top20} layout="vertical" margin={{ left: 160 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" domain={[0, 1]} />
            <YAxis
              dataKey="label"
              type="category"
              width={150}
              tick={{ fontSize: 11 }}
            />
            <Tooltip
              formatter={(v) => [`${(v * 100).toFixed(1)}%`, "Risk Score"]}
            />
            <Bar dataKey="risk_score" name="Risk Score">
              {top20.map((d, i) => (
                <Cell
                  key={i}
                  fill={PROTOCOL_COLORS[d.protocol] || "#6b7280"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
