import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, RefreshCw, Clock, Play, CheckCircle, AlertTriangle, Circle, XCircle, RotateCcw, Square, ScrollText } from "lucide-react";
import { listEngagements, deleteEngagement, startEngagement } from "../utils/api";

const STATUS_STYLES = {
  created:            { color: "bg-gray-600",   text: "text-gray-100" },
  scheduled:          { color: "bg-blue-600",   text: "text-blue-100" },
  running:            { color: "bg-yellow-600",  text: "text-yellow-100" },
  awaiting_approval:  { color: "bg-orange-600",  text: "text-orange-100" },
  completed:          { color: "bg-green-600",   text: "text-green-100" },
  error:              { color: "bg-red-600",     text: "text-red-100" },
  paused:             { color: "bg-amber-600",   text: "text-amber-100" },
  stopped:            { color: "bg-gray-700",    text: "text-gray-200" },
};

const STATUS_ICONS = {
  created: Circle,
  scheduled: Clock,
  running: Play,
  awaiting_approval: AlertTriangle,
  completed: CheckCircle,
  error: XCircle,
  paused: RotateCcw,
  stopped: Square,
};

const isResumable = (status) => status === "paused" || status === "stopped";

function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.created;
  const Icon = STATUS_ICONS[status] || Circle;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${style.color} ${style.text}`}>
      <Icon className="w-3 h-3" />
      {status.replace(/_/g, " ")}
    </span>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return "--";
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return dateStr;
  }
}

export default function Dashboard({ user, navigate }) {
  const [engagements, setEngagements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [resuming, setResuming] = useState({});

  const fetchEngagements = useCallback(async () => {
    try {
      const data = await listEngagements();
      setEngagements(Array.isArray(data) ? data : data.engagements || []);
      setError("");
    } catch (err) {
      setError(err.message || "Failed to load engagements");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEngagements();
    const interval = setInterval(fetchEngagements, 10000);
    return () => clearInterval(interval);
  }, [fetchEngagements]);

  const handleRowClick = (eng) => {
    if (eng.status === "running") navigate("live", eng.id);
    else if (eng.status === "awaiting_approval") navigate("approval", eng.id);
    else if (eng.status === "completed") navigate("findings", eng.id);
    else navigate("live", eng.id);
  };

  const handleDelete = async (e, eng) => {
    e.stopPropagation();
    if (!confirm(`Delete engagement "${eng.name}"? This cannot be undone.`)) return;
    setDeleting(eng.id);
    try {
      await deleteEngagement(eng.id);
      setEngagements((prev) => prev.filter((en) => en.id !== eng.id));
    } catch (err) {
      setError(err.message || "Failed to delete");
    } finally {
      setDeleting(null);
    }
  };

  const handleResume = async (e, eng) => {
    e.stopPropagation();
    setResuming((prev) => ({ ...prev, [eng.id]: true }));
    try {
      await startEngagement(eng.id);
      await fetchEngagements();
    } catch (err) {
      setError(err.message || "Failed to resume engagement");
    } finally {
      setResuming((prev) => ({ ...prev, [eng.id]: false }));
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-100">Engagements</h2>
          <p className="text-sm text-gray-400 mt-1">
            {engagements.length} engagement{engagements.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchEngagements}
            className="p-2 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate("setup")}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Engagement
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-4 py-3 mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center text-gray-400 py-20">Loading engagements...</div>
      ) : engagements.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-gray-400 mb-4">No engagements yet</p>
          <button
            onClick={() => navigate("setup")}
            className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-medium transition-colors"
          >
            Create your first engagement
          </button>
        </div>
      ) : (
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-left">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Current Phase</th>
                <th className="px-4 py-3 font-medium">Scheduled</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium w-24"></th>
              </tr>
            </thead>
            <tbody>
              {engagements.map((eng) => (
                <tr
                  key={eng.id}
                  onClick={() => handleRowClick(eng)}
                  className="border-b border-gray-800/50 hover:bg-gray-800/50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-gray-100">{eng.name}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={eng.status} />
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {eng.current_phase || "--"}
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {formatDate(eng.scheduled_at)}
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {formatDate(eng.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      {isResumable(eng.status) && (
                        <button
                          onClick={(e) => handleResume(e, eng)}
                          disabled={resuming[eng.id]}
                          className="p-1.5 text-gray-500 hover:text-blue-400 hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                          title="Resume engagement"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); navigate("logs", eng.id); }}
                        className="p-1.5 text-gray-500 hover:text-blue-400 hover:bg-gray-700 rounded transition-colors"
                        title="View tool logs"
                      >
                        <ScrollText className="w-4 h-4" />
                      </button>
                      <button
                        onClick={(e) => handleDelete(e, eng)}
                        disabled={deleting === eng.id}
                        className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                        title="Delete engagement"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
