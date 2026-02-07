import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";
import { Card, CardHeader, CardContent } from "../ui/card";
import { CHART_COLORS } from "../../utils/chartColors";

export default function VulnsByTypeChart({ data }) {
  if (!data || data.length === 0) return null;

  const sorted = [...data].sort((a, b) => b.vulns_found - a.vulns_found);

  return (
    <Card>
      <CardHeader>Vulnerabilidades por Tipo de Teste</CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={Math.max(300, sorted.length * 35)}>
          <BarChart data={sorted} layout="vertical" margin={{ left: 120 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis
              dataKey="test_type"
              type="category"
              width={110}
              tick={{ fontSize: 12 }}
            />
            <Tooltip
              formatter={(value, name) => [
                value,
                name === "vulns_found" ? "Vulnerabilidades" : "Testes",
              ]}
            />
            <Bar dataKey="vulns_found" name="Vulnerabilidades">
              {sorted.map((_, i) => (
                <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
