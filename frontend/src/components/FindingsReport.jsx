import React, { useState, useEffect, useRef } from "react";
import { ArrowLeft, Download, ChevronUp, ChevronDown, Loader2, ThumbsUp, ThumbsDown, Edit2, ScrollText } from "lucide-react";
import { getFindings, getEngagement, exportFindings, submitFindingFeedback } from "../utils/api";

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
  const [feedbackState, setFeedbackState] = useState({});
  const [colWidths, setColWidths] = useState([110, 180, 300, 120, 180]);
  const dragRef = useRef(null);

  useEffect(() => {
    const onMove = (e) => {
      if (!dragRef.current) return;
      const { idx, startX, startW } = dragRef.current;
      const delta = e.clientX - startX;
      setColWidths((prev) => {
        const next = [...prev];
        next[idx] = Math.max(60, startW + delta);
        return next;
      });
    };
    const onUp = () => {
      dragRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, []);

  const startDrag = (e, idx) => {
    e.preventDefault();
    dragRef.current = { idx, startX: e.clientX, startW: colWidths[idx] };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const getFb = (id) => feedbackState[id] || { mode: null, reason: "", rewordedTitle: "", rewordedDescription: "", done: false };
  const setFb = (id, patch) => setFeedbackState((prev) => ({ ...prev, [id]: { ...getFb(id), ...patch } }));

  const handleAccept = async (finding) => {
    await submitFindingFeedback(engagementId, finding.id, { action: "accepted" }).catch(() => {});
    setFb(finding.id, { done: true, mode: null });
  };

  const handleRejectSubmit = async (finding) => {
    const fb = getFb(finding.id);
    if (!fb.reason.trim()) return;
    await submitFindingFeedback(engagementId, finding.id, {
      action: "rejected", rejection_reason: fb.reason,
    }).catch(() => {});
    setFb(finding.id, { done: true, mode: null });
  };

  const handleRewordSubmit = async (finding) => {
    const fb = getFb(finding.id);
    if (!fb.rewordedTitle.trim()) return;
    await submitFindingFeedback(engagementId, finding.id, {
      action: "reworded",
      reworded_title: fb.rewordedTitle,
      reworded_description: fb.rewordedDescription,
    }).catch(() => {});
    // Update local finding display to show reworded version
    setFindings((prev) => prev.map((f) =>
      f.id === finding.id
        ? { ...f, title: fb.rewordedTitle, description: fb.rewordedDescription || f.description }
        : f
    ));
    setFb(finding.id, { done: true, mode: null });
  };

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
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("logs", engagementId)}
            className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-gray-200 px-4 py-2 rounded-lg font-medium transition-colors"
          >
            <ScrollText className="w-4 h-4" />
            Tool Logs
          </button>
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
          <table className="w-full text-sm table-fixed">
            <colgroup>
              {colWidths.map((w, i) => <col key={i} style={{ width: w }} />)}
            </colgroup>
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-left">
                {[
                  { label: "Severity", field: "severity", idx: 0 },
                  { label: "Title", field: "title", idx: 1 },
                  { label: "Description", field: null, idx: 2 },
                  { label: "Phase", field: "phase", idx: 3 },
                  { label: "Exploitation Result", field: null, idx: 4 },
                ].map(({ label, field, idx }) => (
                  <th
                    key={label}
                    className="px-4 py-3 font-medium relative select-none overflow-hidden"
                    onClick={field ? () => handleSort(field) : undefined}
                    style={field ? { cursor: "pointer" } : undefined}
                  >
                    <span className={field ? "hover:text-gray-200" : ""}>
                      {label} {field && <SortIcon field={field} />}
                    </span>
                    {idx < 4 && (
                      <div
                        onMouseDown={(e) => startDrag(e, idx)}
                        className="absolute right-0 top-0 bottom-0 w-3 cursor-col-resize group flex items-center justify-center"
                      >
                        <div className="w-px h-4 bg-gray-600 group-hover:bg-blue-400 group-hover:h-full transition-all" />
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedFindings.map((f, i) => {
                const sev = (f.severity || "info").toLowerCase();
                return (
                  <React.Fragment key={f.id || i}>
                    <tr className="border-b border-gray-800/50 hover:bg-gray-800/30">
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
                    <tr key={`${f.id || i}-fb`} className="border-b border-gray-800/50">
                      <td colSpan={5} className="px-4 pb-3">
                        {(() => {
                          const fb = getFb(f.id);
                          if (fb.done) {
                            return <p className="text-xs text-green-500">Feedback recorded.</p>;
                          }
                          return (
                            <div>
                              {fb.mode === null && (
                                <div className="flex items-center gap-2">
                                  <span className="text-xs text-gray-500">Feedback:</span>
                                  <button
                                    onClick={() => handleAccept(f)}
                                    className="flex items-center gap-1 text-xs text-green-400 hover:text-green-300 bg-green-900/20 border border-green-800/40 px-2 py-0.5 rounded transition-colors"
                                  >
                                    <ThumbsUp className="w-3 h-3" /> Accept
                                  </button>
                                  <button
                                    onClick={() => setFb(f.id, { mode: "reject" })}
                                    className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 bg-red-900/20 border border-red-800/40 px-2 py-0.5 rounded transition-colors"
                                  >
                                    <ThumbsDown className="w-3 h-3" /> Reject
                                  </button>
                                  <button
                                    onClick={() => setFb(f.id, { mode: "reword", rewordedTitle: f.title, rewordedDescription: f.description || "" })}
                                    className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 bg-blue-900/20 border border-blue-800/40 px-2 py-0.5 rounded transition-colors"
                                  >
                                    <Edit2 className="w-3 h-3" /> Reword
                                  </button>
                                </div>
                              )}
                              {fb.mode === "reject" && (
                                <div className="flex items-center gap-2">
                                  <input
                                    autoFocus
                                    value={fb.reason}
                                    onChange={(e) => setFb(f.id, { reason: e.target.value })}
                                    placeholder="Reason for rejection..."
                                    className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-red-600"
                                  />
                                  <button
                                    onClick={() => handleRejectSubmit(f)}
                                    disabled={!getFb(f.id).reason.trim()}
                                    className="text-xs text-red-400 hover:text-red-300 disabled:opacity-40 px-2 py-1 rounded border border-red-800/40 transition-colors"
                                  >
                                    Submit
                                  </button>
                                  <button onClick={() => setFb(f.id, { mode: null })} className="text-xs text-gray-500 hover:text-gray-300">
                                    Cancel
                                  </button>
                                </div>
                              )}
                              {fb.mode === "reword" && (
                                <div className="space-y-2">
                                  <input
                                    autoFocus
                                    value={getFb(f.id).rewordedTitle}
                                    onChange={(e) => setFb(f.id, { rewordedTitle: e.target.value })}
                                    placeholder="Reworded title..."
                                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:border-blue-600"
                                  />
                                  <textarea
                                    value={getFb(f.id).rewordedDescription}
                                    onChange={(e) => setFb(f.id, { rewordedDescription: e.target.value })}
                                    placeholder="Reworded description (optional)..."
                                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 resize-y min-h-[60px] focus:outline-none focus:border-blue-600"
                                  />
                                  <div className="flex gap-2">
                                    <button
                                      onClick={() => handleRewordSubmit(f)}
                                      disabled={!getFb(f.id).rewordedTitle.trim()}
                                      className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-40 px-2 py-1 rounded border border-blue-800/40 transition-colors"
                                    >
                                      Save
                                    </button>
                                    <button onClick={() => setFb(f.id, { mode: null })} className="text-xs text-gray-500 hover:text-gray-300">
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </td>
                    </tr>
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
