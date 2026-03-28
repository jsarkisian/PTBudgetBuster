import React, { useState, useEffect } from "react";
import {
  ArrowLeft, Download, ChevronRight, ChevronDown,
  Check, XCircle, Loader2, ScrollText,
} from "lucide-react";
import { getToolResults, getEngagement, exportFull } from "../utils/api";

const PHASES = ["ALL", "RECON", "ENUMERATION", "VULN_SCAN", "ANALYSIS", "EXPLOITATION"];

const PHASE_COLORS = {
  RECON:        "bg-blue-900/50 text-blue-300 border-blue-800/50",
  ENUMERATION:  "bg-purple-900/50 text-purple-300 border-purple-800/50",
  VULN_SCAN:    "bg-yellow-900/50 text-yellow-300 border-yellow-800/50",
  ANALYSIS:     "bg-orange-900/50 text-orange-300 border-orange-800/50",
  EXPLOITATION: "bg-red-900/50 text-red-300 border-red-800/50",
};

function fmtDuration(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return "<1s";
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.round((ms % 60000) / 1000);
  return `${m}m ${s}s`;
}

function fmtTime(iso) {
  if (!iso) return "--";
  try { return new Date(iso).toLocaleTimeString(); } catch { return iso; }
}

function StatusIcon({ status }) {
  if (status === "success") return <Check className="w-3.5 h-3.5 text-green-400" />;
  if (status === "error" || status === "timeout") return <XCircle className="w-3.5 h-3.5 text-red-400" />;
  return <Loader2 className="w-3.5 h-3.5 text-gray-400 animate-spin" />;
}

export default function ToolLogs({ engagementId, navigate }) {
  const [toolResults, setToolResults] = useState([]);
  const [engagement, setEngagement] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [phaseFilter, setPhaseFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [toolFilter, setToolFilter] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportingFull, setExportingFull] = useState(false);

  useEffect(() => {
    Promise.all([getToolResults(engagementId), getEngagement(engagementId)])
      .then(([results, eng]) => {
        setToolResults(Array.isArray(results) ? results : []);
        setEngagement(eng);
      })
      .catch((err) => setError(err.message || "Failed to load tool logs"))
      .finally(() => setLoading(false));
  }, [engagementId]);

  const filtered = toolResults.filter((r) => {
    if (phaseFilter !== "ALL" && r.phase !== phaseFilter) return false;
    if (statusFilter !== "ALL" && r.status !== statusFilter) return false;
    if (toolFilter && !r.tool.toLowerCase().includes(toolFilter.toLowerCase())) return false;
    return true;
  });

  const errorCount = filtered.filter((r) => r.status === "error" || r.status === "timeout").length;

  const handleExportLogs = async () => {
    setExporting(true);
    try {
      const blob = new Blob([JSON.stringify(toolResults, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tool-results-${engagementId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  const handleExportFull = async () => {
    setExportingFull(true);
    try {
      const data = await exportFull(engagementId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `full-export-${engagementId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Export failed");
    } finally {
      setExportingFull(false);
    }
  };

  const toggleExpand = (id) => setExpandedId((prev) => (prev === id ? null : id));

  const phaseClass = (phase) =>
    PHASE_COLORS[phase] || "bg-gray-800 text-gray-400 border-gray-700";

  return (
    <div className="max-w-7xl mx-auto p-6">
      <button
        onClick={() => navigate("dashboard")}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <ScrollText className="w-5 h-5 text-gray-400 shrink-0" />
          <div>
            <h2 className="text-xl font-bold text-gray-100">Tool Logs</h2>
            {engagement && (
              <p className="text-sm text-gray-400 mt-0.5">{engagement.name}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportLogs}
            disabled={exporting || toolResults.length === 0}
            className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-600 text-gray-200 text-sm px-3 py-1.5 rounded-lg transition-colors"
          >
            {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            Export Logs
          </button>
          <button
            onClick={handleExportFull}
            disabled={exportingFull || toolResults.length === 0}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-600 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
          >
            {exportingFull ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            Export Full
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4">
        <select
          value={phaseFilter}
          onChange={(e) => setPhaseFilter(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-blue-600"
        >
          {PHASES.map((p) => <option key={p} value={p}>{p === "ALL" ? "All Phases" : p}</option>)}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-blue-600"
        >
          <option value="ALL">All Statuses</option>
          <option value="success">Success</option>
          <option value="error">Error</option>
          <option value="running">Running</option>
        </select>
        <input
          type="text"
          value={toolFilter}
          onChange={(e) => setToolFilter(e.target.value)}
          placeholder="Filter by tool name..."
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-600 w-48"
        />
      </div>

      {!loading && !error && (
        <p className="text-xs text-gray-500 mb-3">
          {filtered.length} tool run{filtered.length !== 1 ? "s" : ""}
          {errorCount > 0 && (
            <span className="text-red-400 ml-1">· {errorCount} error{errorCount !== 1 ? "s" : ""}</span>
          )}
        </p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-4 py-3 mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          Loading tool logs...
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20 text-gray-400">No tool runs match the current filters.</div>
      ) : (
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-left">
                <th className="px-4 py-3 font-medium w-32">Phase</th>
                <th className="px-4 py-3 font-medium">Tool</th>
                <th className="px-4 py-3 font-medium w-24">Status</th>
                <th className="px-4 py-3 font-medium w-20">Duration</th>
                <th className="px-4 py-3 font-medium w-24">Time</th>
                <th className="px-4 py-3 font-medium w-8"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const isError = r.status === "error" || r.status === "timeout";
                const isExpanded = expandedId === r.id;
                const params = r.input || {};
                const paramStr = typeof params === "object"
                  ? JSON.stringify(params, null, 2)
                  : String(params);

                return (
                  <React.Fragment key={r.id}>
                    <tr
                      onClick={() => toggleExpand(r.id)}
                      className={`border-b border-gray-800/50 cursor-pointer hover:bg-gray-800/30 transition-colors ${isError ? "border-l-2 border-l-red-700/50" : ""}`}
                    >
                      <td className="px-4 py-3">
                        <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded border ${phaseClass(r.phase)}`}>
                          {r.phase}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-100 font-mono text-xs">{r.tool}</td>
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-1.5">
                          <StatusIcon status={r.status} />
                          <span className={`text-xs ${isError ? "text-red-400" : r.status === "success" ? "text-green-400" : "text-gray-400"}`}>
                            {r.status}
                          </span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">{fmtDuration(r.duration_ms)}</td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{fmtTime(r.created_at)}</td>
                      <td className="px-4 py-3 text-gray-600">
                        {isExpanded
                          ? <ChevronDown className="w-3.5 h-3.5" />
                          : <ChevronRight className="w-3.5 h-3.5" />}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${r.id}-detail`} className="border-b border-gray-800/50 bg-gray-950/50">
                        <td colSpan={6} className="px-4 py-4 space-y-3">
                          {/* Parameters */}
                          <div>
                            <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Parameters</p>
                            <pre className="text-xs text-gray-300 bg-gray-800/60 rounded p-3 overflow-x-auto whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
                              {paramStr}
                            </pre>
                          </div>

                          {/* Output */}
                          {r.output && (
                            <div>
                              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Output</p>
                              <pre className="text-xs text-gray-300 bg-gray-800/60 rounded p-3 overflow-x-auto whitespace-pre-wrap break-all max-h-64 overflow-y-auto">
                                {r.output}
                              </pre>
                            </div>
                          )}

                          {/* Stderr */}
                          {r.error && (
                            <div>
                              <p className="text-[10px] font-semibold text-red-500 uppercase tracking-wide mb-1">Stderr</p>
                              <pre className="text-xs text-red-300 bg-red-950/30 border border-red-800/30 rounded p-3 overflow-x-auto whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
                                {r.error}
                              </pre>
                            </div>
                          )}

                          {/* Exit code */}
                          {r.exit_code != null && (
                            <p className="text-xs text-gray-500">
                              Exit code: <span className={r.exit_code === 0 ? "text-green-400" : "text-red-400"}>{r.exit_code}</span>
                              {r.completed_at && (
                                <span className="ml-4">Completed: {new Date(r.completed_at).toLocaleString()}</span>
                              )}
                            </p>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
