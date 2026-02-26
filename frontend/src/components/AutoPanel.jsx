import React, { useState, useRef, useEffect } from 'react';
import { api } from '../utils/api';

export default function AutoPanel({ session, pendingApproval, autoHistory = [], currentStatus, onStart, onStop, onApprove, onSendMessage }) {
  const [objective, setObjective] = useState('');
  const [maxSteps, setMaxSteps] = useState(10);
  const [playbooks, setPlaybooks] = useState([]);
  const [selectedPlaybook, setSelectedPlaybook] = useState(null);
  const [approvalMode, setApprovalMode] = useState('manual');
  const [chatInput, setChatInput] = useState('');
  const [sending, setSending] = useState(false);
  const historyRef = useRef(null);
  const chatInputRef = useRef(null);
  const isRunning = session?.auto_mode;
  const step = session?.auto_current_step || 0;
  const maxS = session?.auto_max_steps || 10;

  // Auto-scroll history to bottom on new entries
  useEffect(() => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [autoHistory.length]);

  useEffect(() => {
    api.getPlaybooks().then(setPlaybooks).catch(() => {});
  }, []);

  const handleStart = () => {
    if (!objective.trim()) return;
    onStart(objective.trim(), maxSteps, selectedPlaybook?.id || null, approvalMode);
    setObjective('');
  };

  const handleSend = async () => {
    const msg = chatInput.trim();
    if (!msg || sending) return;
    setSending(true);
    setChatInput('');
    try { await onSendMessage(msg); } finally { setSending(false); }
    chatInputRef.current?.focus();
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header / Controls */}
      <div className="p-4 border-b border-dark-600 shrink-0">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-lg">🤖</span>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-200">Autonomous Testing Mode</h3>
            {isRunning && session?.auto_objective && (
              <p className="text-xs text-gray-500 truncate mt-0.5" title={session.auto_objective}>
                {session.auto_objective}
              </p>
            )}
          </div>
          {isRunning && (
            <div className="flex items-center gap-2 shrink-0">
              {session?.auto_phase_count > 0 && (
                <span className="text-xs text-blue-400 font-medium">
                  Phase {session.auto_current_phase || 1}/{session.auto_phase_count}
                </span>
              )}
              <span className="text-xs text-gray-400 font-mono">{step}/{maxS}</span>
              <span className="flex items-center gap-1 text-xs text-accent-green">
                <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
                Running
              </span>
            </div>
          )}
        </div>

        {!isRunning ? (
          <div className="space-y-3">
            <div className="mb-3">
              <label className="block text-sm text-gray-400 mb-1">Mode</label>
              <select
                value={selectedPlaybook?.id || ''}
                onChange={(e) => {
                  const pb = playbooks.find(p => p.id === e.target.value);
                  setSelectedPlaybook(pb || null);
                  if (pb) {
                    setObjective(pb.description);
                    const total = pb.phases.reduce((sum, p) => sum + p.max_steps, 0);
                    setMaxSteps(total);
                    setApprovalMode(pb.approval_default || 'manual');
                  } else {
                    setApprovalMode('manual');
                  }
                }}
                className="w-full bg-gray-700 text-white rounded px-3 py-2"
              >
                <option value="">Freeform (no playbook)</option>
                {playbooks.map(pb => (
                  <option key={pb.id} value={pb.id}>{pb.name}</option>
                ))}
              </select>
            </div>
            {selectedPlaybook && (
              <div className="mb-3 p-2 bg-gray-800 rounded text-sm">
                <div className="font-medium text-gray-300 mb-1">Phases:</div>
                {selectedPlaybook.phases.map((p, i) => (
                  <div key={i} className="text-gray-400 ml-2">
                    {i + 1}. {p.name} <span className="text-gray-500">({p.max_steps} steps)</span>
                  </div>
                ))}
              </div>
            )}
            <div>
              <label className="block text-xs text-gray-400 mb-1 font-medium">Testing Objective</label>
              <textarea
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="e.g., Perform a full external reconnaissance and vulnerability assessment of the target scope. Focus on finding exposed services, misconfigurations, and known CVEs."
                className="input text-xs min-h-[80px]"
                rows={3}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1 font-medium">
                Max Steps: {maxSteps}
              </label>
              <input
                type="range" min={3} max={50} value={maxSteps}
                onChange={(e) => setMaxSteps(parseInt(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>Quick (3)</span>
                <span>Thorough (50)</span>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-300 mb-3">
              <input
                type="checkbox"
                checked={approvalMode === 'auto'}
                onChange={(e) => setApprovalMode(e.target.checked ? 'auto' : 'manual')}
                className="rounded"
              />
              Auto-approve steps
            </label>
            <button onClick={handleStart} disabled={!objective.trim()} className="btn-success w-full">
              Start Autonomous Testing
            </button>
          </div>
        ) : (
          <button onClick={onStop} className="btn-danger w-full">
            Stop Autonomous Mode
          </button>
        )}
      </div>

      {/* History feed */}
      <div ref={historyRef} className="flex-1 overflow-y-auto p-3 space-y-2">
        {autoHistory.length === 0 && !isRunning ? (
          <div className="text-center py-12 text-gray-500">
            <div className="text-3xl mb-2">🎯</div>
            <p className="text-sm">Configure an objective and start autonomous testing.</p>
            <p className="text-xs mt-2 text-gray-600">
              The AI proposes each step for your approval before running anything.
              Nothing executes until you approve it.
            </p>
          </div>
        ) : (
          autoHistory
            // Filter out noisy per-step live messages — those show in the status bar
            .filter(e => e.type !== 'status' || !e.message?.match(/^Step \d+:/))
            .map((entry, i) => {
              if (entry.type === 'phase_change') return (
                <div key={i} className="flex items-center gap-2 py-2 my-1 border-t border-b border-blue-500/30">
                  <span className="bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded text-xs font-medium">
                    Phase {entry.phase_number}/{entry.phase_count}
                  </span>
                  <span className="text-white text-sm font-medium">{entry.phase_name}</span>
                </div>
              );
              if (entry.type === 'status') return <StatusEntry key={i} entry={entry} />;
              if (entry.type === 'user_message') return <UserMessageEntry key={i} entry={entry} />;
              if (entry.type === 'ai_reply') return <AiReplyEntry key={i} entry={entry} />;
              return (
                <StepEntry
                  key={entry.stepId || i}
                  entry={entry}
                  isPending={pendingApproval?.stepId === entry.stepId}
                  onApprove={onApprove}
                />
              );
            })
        )}

      </div>

      {/* Live status bar — only when AI is working (not waiting for approval or reply) */}
      {isRunning && !pendingApproval && currentStatus && (
        <div className="shrink-0 border-t border-dark-600 bg-dark-900/80 px-3 py-1.5">
          <div className="flex items-center gap-2">
            <div className="flex gap-0.5 shrink-0">
              <span className="w-1.5 h-1.5 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-xs text-gray-400 leading-snug truncate">{currentStatus}</span>
          </div>
        </div>
      )}

      {/* Chat input + stop button — always visible while running */}
      {isRunning && (
        <div className="shrink-0 border-t border-dark-600 bg-dark-900 p-3 space-y-2">
          <div className="flex gap-2 items-end">
            <textarea
              ref={chatInputRef}
              value={chatInput}
              onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="Chat with the AI… redirect it, ask questions, or adjust focus (Enter to send)"
              className="input text-xs flex-1 resize-none min-h-[36px] max-h-[100px]"
              rows={1}
              disabled={sending}
            />
            <button
              onClick={handleSend}
              disabled={!chatInput.trim() || sending}
              className="btn-primary text-xs px-3 py-1.5 shrink-0"
            >
              {sending ? '…' : 'Send'}
            </button>
          </div>
          <button
            onClick={onStop}
            className="w-full py-1.5 text-xs font-semibold text-red-400 bg-red-500/10 border border-red-500/30 rounded hover:bg-red-500/20 transition-colors"
          >
            Stop Autonomous Mode
          </button>
        </div>
      )}
    </div>
  );
}

function UserMessageEntry({ entry }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] bg-accent-blue/20 border border-accent-blue/30 rounded-lg px-3 py-2">
        <div className="text-xs text-accent-blue font-medium mb-0.5">
          {entry.user || 'You'}
        </div>
        <div className="text-xs text-gray-200 whitespace-pre-wrap">{entry.message}</div>
      </div>
    </div>
  );
}

function AiReplyEntry({ entry }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] bg-dark-700 border border-dark-600 rounded-lg px-3 py-2">
        <div className="text-xs text-accent-cyan font-medium mb-0.5">AI</div>
        <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed">{entry.message}</div>
      </div>
    </div>
  );
}

function StatusEntry({ entry }) {
  return (
    <div className="flex items-center gap-2 px-1 py-0.5 text-xs text-gray-500">
      <span className="text-gray-700">─</span>
      <span className="flex-1">{entry.message}</span>
      <span className="text-gray-700 shrink-0">
        {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : ''}
      </span>
    </div>
  );
}

function StepEntry({ entry, isPending, onApprove }) {
  const [expanded, setExpanded] = useState(true);

  const isCompleted = entry.status === 'completed';
  const isApproved = entry.status === 'approved';
  const isRejected = entry.status === 'rejected';
  const isExecuting = isApproved && !isCompleted;

  const statusIcon = isCompleted
    ? <span className="text-accent-green font-bold">✓</span>
    : isRejected
    ? <span className="text-accent-red font-bold">✗</span>
    : isExecuting
    ? <span className="text-accent-blue font-bold animate-pulse">▶</span>
    : <span className="text-accent-yellow font-bold">⏳</span>;

  const statusLabel = isCompleted
    ? null
    : isRejected
    ? null
    : isExecuting
    ? <span className="text-xs text-accent-blue">— Executing…</span>
    : <span className="text-xs text-accent-yellow">— Approve this proposal?</span>;

  const borderColor = isCompleted
    ? 'border-accent-green/20'
    : isRejected
    ? 'border-accent-red/20'
    : isExecuting
    ? 'border-accent-blue/30'
    : 'border-accent-yellow/40';

  const headerBg = isCompleted
    ? 'bg-green-500/5'
    : isRejected
    ? 'bg-red-500/5'
    : isExecuting
    ? 'bg-blue-500/5'
    : 'bg-yellow-500/8';

  // Extract tool names for collapsed summary
  const toolNames = (entry.toolCalls || [])
    .map(tc => tc.input?.tool || (tc.tool === 'execute_bash' ? 'bash' : tc.tool))
    .filter(Boolean)
    .filter((v, i, a) => a.indexOf(v) === i)
    .slice(0, 4);

  return (
    <div className={`border rounded ${borderColor} overflow-hidden`}>
      {/* Step header — click to expand/collapse */}
      <button
        onClick={() => setExpanded(e => !e)}
        className={`w-full flex items-center gap-2 px-3 py-2 text-left ${headerBg} hover:brightness-110 transition-all`}
      >
        <span className="text-xs shrink-0">{statusIcon}</span>
        <span className="text-xs font-semibold text-gray-200 shrink-0">Step {entry.stepNumber}</span>
        {statusLabel}
        {toolNames.length > 0 && (
          <span className="ml-auto text-xs text-gray-600 font-mono truncate max-w-[120px]">
            {toolNames.join(', ')}
          </span>
        )}
        <span className="text-gray-600 text-xs shrink-0">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 pt-2 space-y-3 bg-dark-800/40">
          {/* Proposal label */}
          <div className="text-xs text-gray-500 font-medium uppercase tracking-wide">
            {isPending ? 'Proposed action' : 'Proposal'}
          </div>

          {/* AI proposal / description */}
          <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
            {entry.description || <span className="text-gray-600 italic">No description provided</span>}
          </div>

          {/* Approval buttons — shown BEFORE execution */}
          {isPending && (
            <div className="flex gap-2 pt-1 border-t border-dark-600">
              <button
                onClick={() => onApprove(entry.stepId, true)}
                className="btn-success flex-1 text-xs py-1.5"
              >
                ✓ Approve & Execute
              </button>
              <button
                onClick={() => onApprove(entry.stepId, false)}
                className="btn-danger flex-1 text-xs py-1.5"
              >
                ✗ Reject & Stop
              </button>
            </div>
          )}

          {/* Execution results — shown AFTER execution completes */}
          {entry.toolCalls?.length > 0 && (
            <div className="border-t border-dark-600 pt-2">
              <div className="text-xs text-gray-500 font-medium mb-1 uppercase tracking-wide">
                Execution results ({entry.toolCalls.length} tool{entry.toolCalls.length !== 1 ? 's' : ''})
              </div>
              <div className="space-y-1">
                {entry.toolCalls.map((tc, i) => (
                  <ToolCallLine key={i} tc={tc} />
                ))}
              </div>
            </div>
          )}

          {/* Summary — shown after execution */}
          {entry.summary && (
            <div className="border-t border-dark-600 pt-2">
              <div className="text-xs text-gray-500 font-medium mb-1 uppercase tracking-wide">Summary</div>
              <div className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                {entry.summary}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ToolCallLine({ tc }) {
  const [showResult, setShowResult] = useState(false);
  const toolName = tc.input?.tool || (tc.tool === 'execute_bash' ? 'bash' : tc.tool) || 'unknown';
  const command = tc.input?.command;
  const params = tc.input?.parameters || {};
  const rawArgs = params.__raw_args__;
  const result = tc.result_preview;

  // Build brief param display
  let paramStr = '';
  if (command) {
    paramStr = command.length > 70 ? command.slice(0, 70) + '…' : command;
  } else if (rawArgs) {
    paramStr = rawArgs.length > 70 ? rawArgs.slice(0, 70) + '…' : rawArgs;
  } else {
    paramStr = Object.entries(params)
      .filter(([k]) => !['__raw_args__', '__scope__'].includes(k))
      .slice(0, 3)
      .map(([k, v]) => `${k}=${String(v).slice(0, 20)}`)
      .join(' ');
  }

  return (
    <div className="text-xs bg-dark-900/80 rounded border border-dark-700">
      <div className="flex items-center gap-2 px-2 py-1">
        <span className="text-accent-cyan font-mono shrink-0">{toolName}</span>
        {paramStr && (
          <span className="text-gray-500 font-mono truncate flex-1">{paramStr}</span>
        )}
        {result && (
          <button
            onClick={() => setShowResult(r => !r)}
            className="text-gray-600 hover:text-gray-400 shrink-0 underline"
          >
            {showResult ? 'hide' : 'result'}
          </button>
        )}
      </div>
      {showResult && result && (
        <div className="px-2 pb-2 text-gray-500 font-mono whitespace-pre-wrap text-xs border-t border-dark-700 max-h-32 overflow-y-auto">
          {result}
        </div>
      )}
    </div>
  );
}
