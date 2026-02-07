import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Card, CardHeader, CardContent } from "../ui/card";
import { STRATEGY_COLORS } from "../../utils/chartColors";

export default function VulnsByProtocolChart({ data }) {
  if (!data || data.length === 0) return null;

  const pivoted = {};
  data.forEach(({ protocol, test_strategy, vulns_found }) => {
    if (!pivoted[protocol]) {
      pivoted[protocol] = { protocol, static_vulns: 0, automl_vulns: 0 };
    }
    if (test_strategy === "static") {
      pivoted[protocol].static_vulns = vulns_found;
    } else {
      pivoted[protocol].automl_vulns = vulns_found;
    }
  });

  const chartData = Object.values(pivoted).sort(
    (a, b) => (b.static_vulns + b.automl_vulns) - (a.static_vulns + a.automl_vulns)
  );

  return (
    <Card>
      <CardHeader>Vulnerabilidades por Protocolo</CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="protocol" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="static_vulns" name="Static" fill={STRATEGY_COLORS.static} />
            <Bar dataKey="automl_vulns" name="AutoML" fill={STRATEGY_COLORS.automl} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
