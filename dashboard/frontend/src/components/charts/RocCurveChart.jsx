import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";
import { Card, CardHeader, CardContent } from "../ui/card";

export default function RocCurveChart({ rocData, cvMetrics }) {
  if (!rocData || !rocData.fpr || !rocData.tpr) return null;

  // Build chart data from fpr/tpr arrays
  const chartData = rocData.fpr.map((fpr, i) => ({
    fpr: fpr,
    tpr: rocData.tpr[i] || 0,
  }));

  // Add diagonal reference points (random classifier)
  const diagonalData = [
    { fpr: 0, random: 0 },
    { fpr: 1, random: 1 },
  ];

  const auc = rocData.auc;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <span>ROC Curve (Cross-Validation)</span>
          {auc != null && (
            <span className="text-sm font-mono bg-blue-100 text-blue-800 px-2 py-1 rounded">
              AUC = {auc.toFixed(4)}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {/* Classification metrics summary */}
        {cvMetrics && (
          <div className="grid grid-cols-4 gap-3 mb-4">
            {cvMetrics.cv_precision && (
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-xs text-gray-500">Precision</div>
                <div className="text-lg font-semibold">
                  {(cvMetrics.cv_precision.mean * 100).toFixed(1)}%
                </div>
              </div>
            )}
            {cvMetrics.cv_recall && (
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-xs text-gray-500">Recall</div>
                <div className="text-lg font-semibold">
                  {(cvMetrics.cv_recall.mean * 100).toFixed(1)}%
                </div>
              </div>
            )}
            {cvMetrics.cv_f1 && (
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-xs text-gray-500">F1-Score</div>
                <div className="text-lg font-semibold">
                  {(cvMetrics.cv_f1.mean * 100).toFixed(1)}%
                </div>
              </div>
            )}
            {cvMetrics.cv_auc && (
              <div className="text-center p-2 bg-gray-50 rounded">
                <div className="text-xs text-gray-500">CV AUC</div>
                <div className="text-lg font-semibold">
                  {(cvMetrics.cv_auc.mean * 100).toFixed(1)}%
                </div>
              </div>
            )}
          </div>
        )}

        <ResponsiveContainer width="100%" height={400}>
          <LineChart margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="fpr"
              type="number"
              domain={[0, 1]}
              label={{ value: "False Positive Rate (1 - Specificity)", position: "insideBottom", offset: -5 }}
              tickFormatter={(v) => v.toFixed(1)}
            />
            <YAxis
              type="number"
              domain={[0, 1]}
              label={{ value: "True Positive Rate (Sensitivity)", angle: -90, position: "insideLeft" }}
              tickFormatter={(v) => v.toFixed(1)}
            />
            <Tooltip
              formatter={(value, name) => [
                `${(value * 100).toFixed(1)}%`,
                name === "tpr" ? "TPR (Sensitivity)" : name === "random" ? "Random Classifier" : name,
              ]}
              labelFormatter={(v) => `FPR: ${(v * 100).toFixed(1)}%`}
            />

            {/* Diagonal reference line (random classifier) */}
            <ReferenceLine
              segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
              stroke="#9ca3af"
              strokeDasharray="5 5"
              label={{ value: "Random", position: "end", fill: "#9ca3af", fontSize: 11 }}
            />

            {/* ROC curve */}
            <Line
              data={chartData}
              type="monotone"
              dataKey="tpr"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              name="ROC Curve"
            />
          </LineChart>
        </ResponsiveContainer>

        <p className="text-xs text-gray-500 mt-2 text-center">
          ROC curve from H2O AutoML cross-validation. AUC closer to 1.0 indicates better
          discriminative ability between vulnerable and non-vulnerable test cases.
        </p>
      </CardContent>
    </Card>
  );
}
