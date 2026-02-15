import { useState, useMemo } from "react";
import {
  Search,
  ChevronDown,
  ChevronUp,
  Play,
  Copy,
  Check,
  X,
  Loader2,
  ArrowRight,
} from "lucide-react";

const API_URL =
  window.location.hostname !== "localhost"
    ? "http://dashboard_api:8000"
    : "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Category pills                                                     */
/* ------------------------------------------------------------------ */
const CATEGORY_COLORS = {
  Health: "bg-green-50 text-green-700 border-green-200",
  Experiments: "bg-blue-50 text-blue-700 border-blue-200",
  History: "bg-purple-50 text-purple-700 border-purple-200",
  Analysis: "bg-amber-50 text-amber-700 border-amber-200",
  Logs: "bg-gray-50 text-gray-700 border-gray-200",
  Architecture: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const METHOD_COLORS = {
  GET: "bg-green-100 text-green-800",
  POST: "bg-blue-100 text-blue-800",
  PUT: "bg-amber-100 text-amber-800",
  DELETE: "bg-red-100 text-red-800",
  PATCH: "bg-purple-100 text-purple-800",
};

/* ------------------------------------------------------------------ */
/*  Copy button                                                        */
/* ------------------------------------------------------------------ */
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={handleCopy}
      className="p-1 rounded hover:bg-gray-200 transition text-gray-400 hover:text-gray-600"
      title="Copy"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Try It panel                                                       */
/* ------------------------------------------------------------------ */
function TryItPanel({ endpoint, onClose }) {
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [bodyInput, setBodyInput] = useState(
    endpoint.request_body ? JSON.stringify(endpoint.request_body, null, 2) : ""
  );

  const fullUrl = `${API_URL}${endpoint.path}`;

  const handleExecute = async () => {
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const opts = { method: endpoint.method };
      if (endpoint.method === "POST" && bodyInput) {
        opts.headers = { "Content-Type": "application/json" };
        // Extract just the values/defaults for the request body
        const bodySchema = endpoint.request_body;
        const body = {};
        for (const [key, schema] of Object.entries(bodySchema)) {
          if (schema.default !== undefined) body[key] = schema.default;
          else if (schema.enum) body[key] = schema.enum[0];
          else if (schema.type === "string") body[key] = "";
          else if (schema.type === "int") body[key] = 0;
          else if (schema.type === "array") body[key] = [];
        }
        opts.body = JSON.stringify(body);
      }
      const res = await fetch(fullUrl, opts);
      const data = await res.json();
      setResponse({ status: res.status, data });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-3 border border-blue-200 rounded-xl bg-blue-50/30 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h5 className="text-xs font-semibold text-blue-700 flex items-center gap-1.5">
          <Play className="w-3.5 h-3.5" /> Try It
        </h5>
        <button onClick={onClose} className="p-1 hover:bg-blue-100 rounded transition">
          <X className="w-3.5 h-3.5 text-blue-400" />
        </button>
      </div>

      {/* URL */}
      <div className="flex items-center gap-2">
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${METHOD_COLORS[endpoint.method]}`}>
          {endpoint.method}
        </span>
        <code className="text-xs font-mono text-gray-600 bg-white px-2 py-1 rounded border border-gray-200 flex-1 truncate">
          {fullUrl}
        </code>
      </div>

      {/* Request body (POST only) */}
      {endpoint.method === "POST" && endpoint.request_body && (
        <div>
          <label className="text-[10px] font-medium text-gray-500 block mb-1">Request Body</label>
          <div className="bg-white border border-gray-200 rounded-lg p-2 text-xs font-mono text-gray-600">
            {Object.entries(endpoint.request_body).map(([key, schema]) => (
              <div key={key} className="flex items-center gap-2 py-0.5">
                <span className="text-blue-600">{key}</span>
                <span className="text-gray-400">:</span>
                <span className="text-gray-500">
                  {schema.type}
                  {schema.default !== undefined && (
                    <span className="text-green-600 ml-1">(default: {JSON.stringify(schema.default)})</span>
                  )}
                  {schema.enum && (
                    <span className="text-amber-600 ml-1">[{schema.enum.join(" | ")}]</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Execute button */}
      <button
        onClick={handleExecute}
        disabled={loading}
        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
      >
        {loading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Play className="w-3.5 h-3.5" />
        )}
        {loading ? "Sending..." : "Send Request"}
      </button>

      {/* Error */}
      {error && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg p-2">
          Error: {error}
        </div>
      )}

      {/* Response */}
      {response && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-medium text-gray-500">
              Response &middot;{" "}
              <span className={response.status < 400 ? "text-green-600" : "text-red-600"}>
                {response.status}
              </span>
            </span>
            <CopyButton text={JSON.stringify(response.data, null, 2)} />
          </div>
          <pre className="bg-gray-900 text-green-400 text-[11px] font-mono p-3 rounded-lg overflow-auto max-h-64 leading-relaxed">
            {JSON.stringify(response.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Endpoint card                                                      */
/* ------------------------------------------------------------------ */
function EndpointCard({ endpoint }) {
  const [expanded, setExpanded] = useState(false);
  const [showTryIt, setShowTryIt] = useState(false);

  const curlExample = endpoint.method === "POST"
    ? `curl -X POST ${API_URL}${endpoint.path} \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(
        Object.fromEntries(
          Object.entries(endpoint.request_body || {}).map(([k, v]) => [
            k,
            v.default !== undefined ? v.default : v.enum ? v.enum[0] : "",
          ])
        )
      )}'`
    : `curl ${API_URL}${endpoint.path}`;

  const jsExample = endpoint.method === "POST"
    ? `const res = await fetch("${API_URL}${endpoint.path}", {\n  method: "POST",\n  headers: { "Content-Type": "application/json" },\n  body: JSON.stringify(${JSON.stringify(
        Object.fromEntries(
          Object.entries(endpoint.request_body || {}).map(([k, v]) => [
            k,
            v.default !== undefined ? v.default : v.enum ? v.enum[0] : "",
          ])
        )
      )})\n});\nconst data = await res.json();`
    : `const res = await fetch("${API_URL}${endpoint.path}");\nconst data = await res.json();`;

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden transition-all hover:border-gray-300 hover:shadow-sm">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
      >
        <span className={`text-[10px] font-bold px-2.5 py-1 rounded-md shrink-0 ${METHOD_COLORS[endpoint.method]}`}>
          {endpoint.method}
        </span>
        <code className="text-sm font-mono text-gray-700 font-medium truncate">{endpoint.path}</code>
        <span className="text-xs text-gray-400 truncate hidden sm:block">{endpoint.summary}</span>
        <span className={`text-[10px] px-2 py-0.5 rounded-full border ml-auto shrink-0 ${CATEGORY_COLORS[endpoint.category] || ""}`}>
          {endpoint.category}
        </span>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-gray-400 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
        )}
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100 pt-3 space-y-3">
          <p className="text-sm text-gray-600">{endpoint.description}</p>

          {/* Parameters */}
          {endpoint.parameters && endpoint.parameters.length > 0 && (
            <div>
              <h5 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Query Parameters
              </h5>
              <div className="space-y-1.5">
                {endpoint.parameters.map((p) => (
                  <div key={p.name} className="flex items-start gap-2 text-xs">
                    <code className="font-mono text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded shrink-0">
                      {p.name}
                    </code>
                    <span className="text-gray-400 shrink-0">{p.type}</span>
                    {p.default !== undefined && p.default !== null && (
                      <span className="text-green-600 shrink-0">= {JSON.stringify(p.default)}</span>
                    )}
                    <span className="text-gray-500">{p.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Request body */}
          {endpoint.request_body && (
            <div>
              <h5 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Request Body
              </h5>
              <div className="bg-gray-50 rounded-lg p-3 space-y-1">
                {Object.entries(endpoint.request_body).map(([key, schema]) => (
                  <div key={key} className="flex items-start gap-2 text-xs">
                    <code className="font-mono text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded shrink-0">
                      {key}
                    </code>
                    <span className="text-gray-400 shrink-0">{schema.type}</span>
                    {schema.default !== undefined && (
                      <span className="text-green-600 shrink-0">= {JSON.stringify(schema.default)}</span>
                    )}
                    {schema.enum && (
                      <span className="text-amber-600 shrink-0">[{schema.enum.join(" | ")}]</span>
                    )}
                    {schema.description && (
                      <span className="text-gray-500">{schema.description}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Response example */}
          {endpoint.response_example && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <h5 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                  Response Example
                </h5>
                <CopyButton text={JSON.stringify(endpoint.response_example, null, 2)} />
              </div>
              <pre className="bg-gray-900 text-green-400 text-[11px] font-mono p-3 rounded-lg overflow-auto max-h-40 leading-relaxed">
                {JSON.stringify(endpoint.response_example, null, 2)}
              </pre>
            </div>
          )}

          {/* Code examples */}
          <div>
            <h5 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Code Examples
            </h5>
            <div className="space-y-2">
              {/* curl */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-medium text-gray-500">curl</span>
                  <CopyButton text={curlExample} />
                </div>
                <pre className="bg-gray-900 text-gray-300 text-[11px] font-mono p-3 rounded-lg overflow-auto max-h-24 leading-relaxed">
                  {curlExample}
                </pre>
              </div>
              {/* JavaScript */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-medium text-gray-500">JavaScript</span>
                  <CopyButton text={jsExample} />
                </div>
                <pre className="bg-gray-900 text-gray-300 text-[11px] font-mono p-3 rounded-lg overflow-auto max-h-24 leading-relaxed">
                  {jsExample}
                </pre>
              </div>
            </div>
          </div>

          {/* Try It button */}
          <div>
            {!showTryIt ? (
              <button
                onClick={() => setShowTryIt(true)}
                className="flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-600 text-xs font-medium rounded-lg hover:bg-blue-100 transition border border-blue-200"
              >
                <Play className="w-3.5 h-3.5" />
                Try It
                <ArrowRight className="w-3 h-3" />
              </button>
            ) : (
              <TryItPanel endpoint={endpoint} onClose={() => setShowTryIt(false)} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main ApiReference component                                        */
/* ------------------------------------------------------------------ */
export default function ApiReference({ metadata }) {
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("All");

  const endpoints = metadata?.api_endpoints || [];

  const categories = useMemo(() => {
    const cats = new Set(endpoints.map((e) => e.category));
    return ["All", ...Array.from(cats)];
  }, [endpoints]);

  const filtered = useMemo(() => {
    return endpoints.filter((e) => {
      const matchesCategory = categoryFilter === "All" || e.category === categoryFilter;
      const matchesSearch =
        !search ||
        e.path.toLowerCase().includes(search.toLowerCase()) ||
        e.summary.toLowerCase().includes(search.toLowerCase()) ||
        e.description.toLowerCase().includes(search.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [endpoints, categoryFilter, search]);

  return (
    <div className="space-y-4">
      {/* Header info */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 className="font-semibold text-gray-800">REST API Documentation</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              {endpoints.length} endpoints &middot; Base URL:{" "}
              <code className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">
                {API_URL}
              </code>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${METHOD_COLORS.GET}`}>
              GET
            </span>
            <span className="text-[10px] text-gray-400">
              {endpoints.filter((e) => e.method === "GET").length}
            </span>
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${METHOD_COLORS.POST}`}>
              POST
            </span>
            <span className="text-[10px] text-gray-400">
              {endpoints.filter((e) => e.method === "POST").length}
            </span>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search endpoints by path or description..."
            className="w-full pl-10 pr-4 py-2.5 text-sm bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-300 transition"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-100 rounded transition"
            >
              <X className="w-3.5 h-3.5 text-gray-400" />
            </button>
          )}
        </div>

        {/* Category pills */}
        <div className="flex flex-wrap gap-1.5">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              className={`text-[11px] font-medium px-3 py-1.5 rounded-lg border transition ${
                categoryFilter === cat
                  ? cat === "All"
                    ? "bg-gray-800 text-white border-gray-800"
                    : CATEGORY_COLORS[cat] || "bg-gray-100 text-gray-700 border-gray-300"
                  : "bg-white text-gray-500 border-gray-200 hover:border-gray-300"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Endpoint list */}
      <div className="space-y-2">
        {filtered.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">
            No endpoints match your filter.
          </div>
        ) : (
          filtered.map((endpoint, i) => (
            <EndpointCard key={`${endpoint.method}-${endpoint.path}-${i}`} endpoint={endpoint} />
          ))
        )}
      </div>

      {/* Footer */}
      <div className="text-center text-[10px] text-gray-400 py-4">
        Powered by FastAPI &middot; All endpoints support CORS &middot; JSON responses
      </div>
    </div>
  );
}
