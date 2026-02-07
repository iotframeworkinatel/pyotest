import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";
import { Card, CardHeader, CardContent } from "../ui/card";
import { CHART_COLORS } from "../../utils/chartColors";

export default function DeviceVulnsChart({ data }) {
  if (!data || data.length === 0) return null;

  const byDevice = {};
  data.forEach(({ container_id, vulns_found, total_tests, protocol }) => {
    if (!byDevice[container_id]) {
      byDevice[container_id] = {
        device: container_id,
        vulns: 0,
        tests: 0,
        protocols: new Set(),
      };
    }
    byDevice[container_id].vulns += vulns_found;
    byDevice[container_id].tests += total_tests;
    byDevice[container_id].protocols.add(protocol);
  });

  const chartData = Object.values(byDevice)
    .map((d) => ({ ...d, protocols: [...d.protocols].join(", ") }))
    .sort((a, b) => b.vulns - a.vulns);

  return (
    <Card>
      <CardHeader>Vulnerabilidades por Dispositivo</CardHeader>
      <CardContent>
        <ResponsiveContainer
          width="100%"
          height={Math.max(250, chartData.length * 40)}
        >
          <BarChart data={chartData} layout="vertical" margin={{ left: 100 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis
              dataKey="device"
              type="category"
              width={90}
              tick={{ fontSize: 11 }}
            />
            <Tooltip
              content={({ payload }) => {
                if (!payload || !payload.length) return null;
                const d = payload[0].payload;
                return (
                  <div className="bg-white shadow-lg rounded p-3 text-sm border">
                    <p className="font-bold">{d.device}</p>
                    <p>Vulns: {d.vulns} / {d.tests} testes</p>
                    <p>Protocolos: {d.protocols}</p>
                  </div>
                );
              }}
            />
            <Bar dataKey="vulns" name="Vulnerabilidades">
              {chartData.map((_, i) => (
                <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
