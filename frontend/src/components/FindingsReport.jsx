import { useState, useEffect } from "react";
import { ArrowLeft, Download, ChevronUp, ChevronDown, Loader2 } from "lucide-react";
import { getFindings, getEngagement, exportFindings } from "../utils/api";

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

const SEVERITY_COLORS = {
  critical: "bg-red-600 text-red-100",
  high: "bg-orange-600 text-orange-100",
  medium: "bg-yellow-600 text-yellow-100",
  low: "bg-blue-600 text-blue-100",
  info: "bg-gray-600 text-gray-100",
};

export default function FindingsReport({ engagementId, navigate }) {
  const [findings, setFindings] = useState([]);
  const [engagement, setEngagement] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sortField, setSortField] = useState("severity");
  const [sortAsc, setSortAsc] = useState(true);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    Promise.all([
      getFindings(engagementId),
      getEngagement(engagementId),
    ])
      .then(([findingsData, engData]) => {
        const list = Array.isArray(findingsData) ? findingsData : findingsData.findings || [];
        setFindings(list);
        setEngagement(engData);
      })
      .catch((err) => setError(err.message || "Failed to load data"))
      .finally(() => setLoading(false));
  }, [engagementId]);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const sortedFindings = [...findings].sort((a, b) => {
    let cmp = 0;
    if (sortField === "severity") {
      const aVal = SEVERITY_ORDER[(a.severity || "info").toLowerCase()] ?? 5;
      const bVal = SEVERITY_ORDER[(b.severity || "info").toLowerCase()] ?? 5;
      cmp = aVal - bVal;
    } else if (sortField === "title") {
      cmp = (a.title || "").localeCompare(b.title || "");
    } else if (sortField === "phase") {
      cmp = (a.phase || "").localeCompare(b.phase || "");
    }
    return sortAsc ? cmp : -cmp;
  });

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await exportFindings(engagementId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `findings-${engagementId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Export failed");
    } finally {
      setExporting(false);
    }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return null;
    return sortAsc
      ? <ChevronUp className="w-3 h-3 inline ml-1" />
      : <ChevronDown className="w-3 h-3 inline ml-1" />;
  };

  // Count by severity
  const counts = {};
  findings.forEach((f) => {
    const sev = (f.severity || "info").toLowerCase();
    counts[sev] = (counts[sev] || 0) + 1;
  });

  return (
    <div className="max-w-7xl mx-auto p-6">
      <button
        onClick={() => navigate("dashboard")}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-100">
            Findings Report
          </h2>
          {engagement && (
            <p className="text-sm text-gray-400 mt-1">{engagement.name}</p>
          )}
        </div>
        <button
          onClick={handleExport}
          disabled={exporting || findings.length === 0}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white px-4 py-2 rounded-lg font-medium transition-colors"
        >
          {exporting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Download className="w-4 h-4" />
          )}
          Export JSON
        </button>
      </div>

      {/* Severity Summary */}
      {!loading && findings.length > 0 && (
        <div className="flex items-center gap-3 mb-6">
          {Object.entries(SEVERITY_ORDER).map(([sev]) => {
            const count = counts[sev] || 0;
            if (count === 0) return null;
            return (
              <div
                key={sev}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium ${SEVERITY_COLORS[sev]}`}
              >
                <span className="font-bold">{count}</span>
                {sev}
              </div>
            );
          })}
          <div className="text-sm text-gray-400 ml-2">
            {findings.length} total finding{findings.length !== 1 ? "s" : ""}
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-4 py-3 mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          Loading findings...
        </div>
      ) : findings.length === 0 ? (
        <div className="text-center py-20 text-gray-400">No findings recorded for this engagement.</div>
      ) : (
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-left">
                <th
                  className="px-4 py-3 font-medium cursor-pointer hover:text-gray-200 w-28"
                  onClick={() => handleSort("severity")}
                >
                  Severity <SortIcon field="severity" />
                </th>
                <th
                  className="px-4 py-3 font-medium cursor-pointer hover:text-gray-200"
                  onClick={() => handleSort("title")}
                >
                  Title <SortIcon field="title" />
                </th>
                <th className="px-4 py-3 font-medium">Description</th>
                <th
                  className="px-4 py-3 font-medium cursor-pointer hover:text-gray-200 w-32"
                  onClick={() => handleSort("phase")}
                >
                  Phase <SortIcon field="phase" />
                </th>
                <th className="px-4 py-3 font-medium w-48">Exploitation Result</th>
              </tr>
            </thead>
            <tbody>
              {sortedFindings.map((f, i) => {
                const sev = (f.severity || "info").toLowerCase();
                return (
                  <tr key={f.id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-3">
                      <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${SEVERITY_COLORS[sev] || SEVERITY_COLORS.info}`}>
                        {sev}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-100 font-medium">{f.title}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs max-w-md">
                      <p className="line-clamp-3">{f.description || "--"}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-400">{f.phase || "--"}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {f.exploitation_result || f.exploit_result || "--"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
