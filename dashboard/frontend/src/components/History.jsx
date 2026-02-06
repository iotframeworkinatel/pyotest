export default function History({ history }) {
  return (
    <div className="bg-white shadow-md rounded-2xl p-6 max-w-5xl mx-auto">
      <h2 className="text-xl font-semibold mb-6 text-center">
        📜 Histórico de Experimentos
      </h2>
      {history.length ? (
        <ul className="space-y-4">
          {history.map((h, i) => (
            <li
              key={i}
              className={`p-4 rounded-xl border-l-4 ${
                h.mode === "automl"
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-500 bg-gray-50"
              }`}
            >
              <div className="flex justify-between items-center">
                <div>
                  <strong>
                    {h.mode === "automl" ? "🤖 AutoML" : "🧪 Static"}
                  </strong>{" "}
                  <span className="text-sm text-gray-500 ml-2">
                    {h.experiment}
                  </span>
                </div>
                <span className="text-sm text-gray-600">
                  ⏱ {Math.round(h.exec_time_sec / 1000)}s
                </span>
              </div>
              <div className="mt-2 text-sm text-gray-700">
                <p>Testes: {h.tests_executed}</p>
                <p>Vulnerabilidades: {h.vulns_detected}</p>
                <p>Devices: {h.devices}</p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-center text-gray-500">Nenhum histórico disponível.</p>
      )}
    </div>
  );
}
