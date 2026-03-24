import { useState, useEffect, useRef, useCallback } from "react";
import {
  ArrowLeft, Square, Send, CheckCircle, Circle, AlertTriangle,
  Loader2, Terminal, Shield, ChevronDown, ChevronRight, RotateCcw,
} from "lucide-react";
import { getEngagement, stopEngagement, sendMessage, startEngagement } from "../utils/api";
import { connectWS } from "../utils/ws";

const PHASES = [
  { id: "RECON", label: "Recon" },
  { id: "ENUMERATION", label: "Enumeration" },
  { id: "VULN_SCAN", label: "Vuln Scan" },
  { id: "ANALYSIS", label: "Analysis" },
  { id: "EXPLOITATION", label: "Exploitation" },
];

const SEVERITY_COLORS = {
  critical: "bg-red-600 text-red-100",
  high: "bg-orange-600 text-orange-100",
  medium: "bg-yellow-600 text-yellow-100",
  low: "bg-blue-600 text-blue-100",
  info: "bg-gray-600 text-gray-100",
};

const isResumable = (status) => status === "paused" || status === "stopped";

function PhaseBar({ currentPhase, completedPhases, objective }) {
  const currentIdx = PHASES.findIndex((p) => p.id === currentPhase);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-1">
        {PHASES.map((phase, i) => {
          const isCompleted = completedPhases.includes(phase.id);
          const isCurrent = phase.id === currentPhase;
          const isFuture = !isCompleted && !isCurrent;

          let bgColor = "bg-gray-700";
          let textColor = "text-gray-500";
          let Icon = Circle;

          if (isCompleted) {
            bgColor = "bg-green-600";
            textColor = "text-green-100";
            Icon = CheckCircle;
          } else if (isCurrent) {
            bgColor = "bg-yellow-600";
            textColor = "text-yellow-100";
            Icon = Loader2;
          }

          return (
            <div key={phase.id} className="flex items-center flex-1">
              <div className={`flex items-center gap-1.5 px-3 py-2 rounded ${bgColor} ${textColor} text-xs font-medium flex-1 justify-center`}>
                <Icon className={`w-3.5 h-3.5 ${isCurrent ? "animate-spin" : ""}`} />
                {phase.label}
              </div>
              {i < PHASES.length - 1 && (
                <div className={`w-4 h-0.5 ${isCompleted ? "bg-green-600" : "bg-gray-700"}`} />
              )}
            </div>
          );
        })}
      </div>
      {objective && (
        <p className="text-xs text-gray-400 mt-2 px-1">{objective}</p>
      )}
    </div>
  );
}

function LogEntry({ event }) {
  const time = event.timestamp
    ? new Date(event.timestamp).toLocaleTimeString()
    : new Date().toLocaleTimeString();

  let icon = <Terminal className="w-3.5 h-3.5 text-gray-500" />;
  let color = "text-gray-300";
  let label = event.type;
  let detail = "";

  switch (event.type) {
    case "phase_changed":
      icon = <Shield className="w-3.5 h-3.5 text-blue-400" />;
      color = "text-blue-400 font-medium";
      label = `Phase: ${event.phase}`;
      detail = event.objective || "";
      break;
    case "tool_start":
      icon = <Loader2 className="w-3.5 h-3.5 text-yellow-400 animate-spin" />;
      color = "text-yellow-400";
      label = `Running: ${event.tool}`;
      detail = event.args ? JSON.stringify(event.args) : "";
      break;
    case "tool_output":
      color = "text-gray-400 font-mono";
      label = event.data || event.output || "";
      break;
    case "tool_result":
      icon = <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
      color = "text-green-400";
      label = `Result: ${event.tool}`;
      detail = typeof event.output === "string" ? event.output.slice(0, 300) : JSON.stringify(event.output || "").slice(0, 300);
      break;
    case "finding_recorded":
      icon = <AlertTriangle className="w-3.5 h-3.5 text-orange-400" />;
      color = "text-orange-400";
      label = `Finding: ${event.title || event.finding?.title || ""}`;
      detail = event.severity || event.finding?.severity || "";
      break;
    case "exploitation_ready":
      icon = <AlertTriangle className="w-3.5 h-3.5 text-orange-400" />;
      color = "text-orange-300 font-bold";
      label = "Exploitation approval required";
      break;
    case "engagement_complete":
      icon = <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
      color = "text-green-300 font-bold";
      label = "Engagement complete";
      break;
    case "error":
      icon = <AlertTriangle className="w-3.5 h-3.5 text-red-400" />;
      color = "text-red-400";
      label = `Error: ${event.message || event.error || ""}`;
      break;
    default:
      detail = JSON.stringify(event).slice(0, 200);
  }

  return (
    <div className="flex items-start gap-2 py-1 px-2 hover:bg-gray-800/50 text-xs">
      <span className="text-gray-600 shrink-0 pt-0.5">{time}</span>
      <span className="shrink-0 pt-0.5">{icon}</span>
      <div className="min-w-0">
        <span className={color}>{label}</span>
        {detail && <span className="text-gray-500 ml-2 break-all">{detail}</span>}
      </div>
    </div>
  );
}

function FindingSidebar({ findings }) {
  const [expanded, setExpanded] = useState({});

  const toggleExpand = (i) => {
    setExpanded((prev) => ({ ...prev, [i]: !prev[i] }));
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden flex flex-col h-full">
      <div className="px-3 py-2 border-b border-gray-800 text-sm font-medium text-gray-300">
        Findings ({findings.length})
      </div>
      <div className="flex-1 overflow-y-auto">
        {findings.length === 0 && (
          <p className="text-gray-500 text-xs p-3">No findings yet</p>
        )}
        {findings.map((f, i) => {
          const sev = f.severity || f.finding?.severity || "info";
          const title = f.title || f.finding?.title || "Finding";
          const desc = f.description || f.finding?.description || "";
          const evidence = f.evidence || f.finding?.evidence || "";
          const isOpen = expanded[i];

          return (
            <div
              key={i}
              className="border-b border-gray-800/50 px-3 py-2 cursor-pointer hover:bg-gray-800/40"
              onClick={() => toggleExpand(i)}
            >
              <div className="flex items-center gap-2">
                {isOpen ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
                <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${SEVERITY_COLORS[sev] || SEVERITY_COLORS.info}`}>
                  {sev}
                </span>
                <span className="text-xs text-gray-200 truncate">{title}</span>
              </div>
              {isOpen && (
                <div className="mt-2 ml-5 space-y-1">
                  {desc && <p className="text-xs text-gray-400">{desc}</p>}
                  {evidence && (
                    <pre className="text-[10px] text-gray-500 bg-gray-800 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
                      {typeof evidence === "string" ? evidence : JSON.stringify(evidence, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function EngagementLive({ engagementId, navigate }) {
  const [engagement, setEngagement] = useState(null);
  const [events, setEvents] = useState([]);
  const [findings, setFindings] = useState([]);
  const [currentPhase, setCurrentPhase] = useState(null);
  const [completedPhases, setCompletedPhases] = useState([]);
  const [phaseObjective, setPhaseObjective] = useState("");
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [message, setMessage] = useState("");
  const [stopping, setStopping] = useState(false);
  const [resuming, setResuming] = useState(false);
  const logRef = useRef(null);
  const wsRef = useRef(null);

  // Fetch initial engagement data
  useEffect(() => {
    getEngagement(engagementId)
      .then((eng) => {
        setEngagement(eng);
        if (eng.current_phase) setCurrentPhase(eng.current_phase);
        if (eng.status === "awaiting_approval") setAwaitingApproval(true);
        if (eng.status === "completed") setCompleted(true);
      })
      .catch(() => {});
  }, [engagementId]);

  // WebSocket connection
  useEffect(() => {
    const ws = connectWS(engagementId, (event) => {
      setEvents((prev) => [...prev, event]);

      switch (event.type) {
        case "phase_changed":
          if (currentPhase) {
            setCompletedPhases((prev) =>
              prev.includes(currentPhase) ? prev : [...prev, currentPhase]
            );
          }
          setCurrentPhase(event.phase);
          setPhaseObjective(event.objective || "");
          break;
        case "finding_recorded":
          setFindings((prev) => [...prev, event]);
          break;
        case "exploitation_ready":
          setAwaitingApproval(true);
          break;
        case "engagement_complete":
          setCompleted(true);
          break;
        case "auto_mode_changed":
          if (event.enabled) {
            getEngagement(engagementId).then((eng) => {
              setEngagement(eng);
              if (eng.current_phase) setCurrentPhase(eng.current_phase);
            }).catch(() => {});
          }
          break;
      }
    });
    wsRef.current = ws;
    return () => {
      if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
    };
  }, [engagementId]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [events]);

  const handleStop = async () => {
    if (!confirm("Stop this engagement?")) return;
    setStopping(true);
    try {
      await stopEngagement(engagementId);
    } catch {
    } finally {
      setStopping(false);
    }
  };

  const handleResume = async () => {
    setResuming(true);
    try {
      await startEngagement(engagementId);
    } catch (err) {
      setEvents((prev) => [...prev, {
        type: "auto_status",
        message: `Resume failed: ${err.message}`,
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setResuming(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!message.trim()) return;
    try {
      await sendMessage(engagementId, message.trim());
      setMessage("");
    } catch {
    }
  };

  return (
    <div className="h-[calc(100vh-57px)] flex flex-col">
      {/* Top bar */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between bg-gray-900/50 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("dashboard")}
            className="p-1.5 text-gray-400 hover:text-gray-200 hover:bg-gray-800 rounded transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h2 className="text-sm font-bold text-gray-100">
            {engagement?.name || "Engagement"}
          </h2>
        </div>
        {isResumable(engagement?.status) ? (
          <button
            onClick={handleResume}
            disabled={resuming}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm px-3 py-1.5 rounded font-medium transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Resume
          </button>
        ) : (
          <button
            onClick={handleStop}
            disabled={stopping || completed || resuming}
            className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm px-3 py-1.5 rounded font-medium transition-colors"
          >
            <Square className="w-3.5 h-3.5" />
            Stop
          </button>
        )}
      </div>

      {/* Banners */}
      {awaitingApproval && (
        <div className="bg-orange-900/40 border-b border-orange-700 px-4 py-3 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2 text-orange-300 text-sm font-medium">
            <AlertTriangle className="w-4 h-4" />
            Findings ready for review — Approve exploitation to continue
          </div>
          <button
            onClick={() => navigate("approval", engagementId)}
            className="bg-orange-600 hover:bg-orange-500 text-white text-sm px-3 py-1.5 rounded font-medium transition-colors"
          >
            Review & Approve
          </button>
        </div>
      )}
      {completed && (
        <div className="bg-green-900/40 border-b border-green-700 px-4 py-3 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2 text-green-300 text-sm font-medium">
            <CheckCircle className="w-4 h-4" />
            Engagement completed
          </div>
          <button
            onClick={() => navigate("findings", engagementId)}
            className="bg-green-600 hover:bg-green-500 text-white text-sm px-3 py-1.5 rounded font-medium transition-colors"
          >
            View Findings
          </button>
        </div>
      )}

      {/* Phase Progress */}
      <div className="px-4 py-3 shrink-0">
        <PhaseBar
          currentPhase={currentPhase}
          completedPhases={completedPhases}
          objective={phaseObjective}
        />
      </div>

      {/* Main content area */}
      <div className="flex-1 flex gap-4 px-4 pb-4 min-h-0">
        {/* Log output */}
        <div className="flex-1 flex flex-col min-w-0">
          <div
            ref={logRef}
            className="flex-1 bg-gray-900 border border-gray-800 rounded-lg overflow-y-auto font-mono"
          >
            {events.length === 0 && (
              <p className="text-gray-500 text-xs p-4">
                Waiting for events...
              </p>
            )}
            {events.map((ev, i) => (
              <LogEntry key={i} event={ev} />
            ))}
          </div>

          {/* Message input */}
          <form onSubmit={handleSendMessage} className="mt-2 flex gap-2">
            <input
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Send guidance message..."
              className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500 placeholder-gray-600"
            />
            <button
              type="submit"
              className="bg-gray-700 hover:bg-gray-600 text-gray-200 px-3 py-2 rounded transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>

        {/* Findings sidebar */}
        <div className="w-72 shrink-0">
          <FindingSidebar findings={findings} />
        </div>
      </div>
    </div>
  );
}
