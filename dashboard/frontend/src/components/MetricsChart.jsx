import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  CartesianGrid,
} from "recharts";

export default function MetricsChart({ metrics }) {
  if (!metrics || !metrics.length) {
    return <p className="text-center text-gray-500">Nenhuma métrica disponível.</p>;
  }

  const chartData = metrics.map((m) => ({
    mode: m.mode,
    tests: m.tests_executed,
    vulns: m.vulns_detected,
    time: Math.round(m.exec_time_sec / 1000),
  }));

  return (
    <div className="bg-white shadow-md rounded-2xl p-6 max-w-4xl mx-auto mt-10">
      <h2 className="text-xl font-semibold mb-4 text-center">📈 Métricas Comparativas</h2>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="mode" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Bar dataKey="tests" fill="#60a5fa" name="Testes" />
          <Bar dataKey="vulns" fill="#f87171" name="Vulns" />
          <Bar dataKey="time" fill="#34d399" name="Tempo (s)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
