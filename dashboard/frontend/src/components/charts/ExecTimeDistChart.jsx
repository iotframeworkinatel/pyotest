import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Card, CardHeader, CardContent } from "../ui/card";
import { STRATEGY_COLORS } from "../../utils/chartColors";

export default function ExecTimeDistChart({ data }) {
  if (!data || data.length === 0) return null;

  const pivoted = {};
  data.forEach(({ time_bucket, test_strategy, count }) => {
    if (!pivoted[time_bucket]) {
      pivoted[time_bucket] = { bucket: time_bucket, static: 0, automl: 0 };
    }
    pivoted[time_bucket][test_strategy] = count;
  });

  const order = ["<100ms", "100-500ms", "500ms-1s", "1-5s", "5-10s", ">10s"];
  const chartData = order.map(
    (b) => pivoted[b] || { bucket: b, static: 0, automl: 0 }
  );

  return (
    <Card>
      <CardHeader>Distribuição de Tempo de Execução</CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="bucket" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="static" name="Static" fill={STRATEGY_COLORS.static} />
            <Bar dataKey="automl" name="AutoML" fill={STRATEGY_COLORS.automl} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
