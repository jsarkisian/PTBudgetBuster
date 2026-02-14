import React, { useState } from 'react';

export default function AutoPanel({ session, pendingApproval, onStart, onStop, onApprove }) {
  const [objective, setObjective] = useState('');
  const [maxSteps, setMaxSteps] = useState(10);
  const isRunning = session?.auto_mode;

  const handleStart = () => {
    if (!objective.trim()) return;
    onStart(objective.trim(), maxSteps);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Config section */}
      <div className="p-4 border-b border-dark-600">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-lg">🤖</span>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">Autonomous Testing Mode</h3>
            <p className="text-xs text-gray-500">
              The AI will plan and execute tests step-by-step, requiring your approval at each stage.
            </p>
          </div>
          {isRunning && (
            <span className="ml-auto flex items-center gap-1.5 text-xs text-accent-green">
              <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
              Running
            </span>
          )}
        </div>

        {!isRunning ? (
          <div className="space-y-3">
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
                type="range"
                min={3}
                max={50}
                value={maxSteps}
                onChange={(e) => setMaxSteps(parseInt(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>Quick (3)</span>
                <span>Thorough (50)</span>
              </div>
            </div>
            <button
              onClick={handleStart}
              disabled={!objective.trim()}
              className="btn-success w-full"
            >
              Start Autonomous Testing
            </button>
          </div>
        ) : (
          <button onClick={onStop} className="btn-danger w-full">
            Stop Autonomous Mode
          </button>
        )}
      </div>

      {/* Approval section */}
      <div className="flex-1 overflow-y-auto p-4">
        {pendingApproval ? (
          <div className="panel border-accent-yellow/40">
            <div className="panel-header bg-yellow-500/10">
              <div className="flex items-center gap-2">
                <span className="text-accent-yellow">⚠️</span>
                <span className="text-sm font-semibold text-accent-yellow">
                  Step {pendingApproval.stepNumber} — Approval Required
                </span>
              </div>
            </div>
            <div className="p-4">
              <div className="text-sm text-gray-300 whitespace-pre-wrap mb-4">
                {pendingApproval.description}
              </div>

              {pendingApproval.toolCalls?.length > 0 && (
                <div className="mb-4">
                  <div className="text-xs text-gray-400 font-medium mb-2">Planned tool calls:</div>
                  <div className="space-y-1">
                    {pendingApproval.toolCalls.map((tc, i) => (
                      <div key={i} className="text-xs bg-dark-700 rounded px-2 py-1 font-mono">
                        <span className="text-accent-cyan">{tc.tool}</span>
                        {tc.input?.tool && <span className="text-gray-400"> → {tc.input.tool}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={() => onApprove(pendingApproval.stepId, true)}
                  className="btn-success flex-1"
                >
                  ✓ Approve & Continue
                </button>
                <button
                  onClick={() => onApprove(pendingApproval.stepId, false)}
                  className="btn-danger flex-1"
                >
                  ✗ Reject & Stop
                </button>
              </div>
            </div>
          </div>
        ) : isRunning ? (
          <div className="text-center py-8">
            <div className="flex justify-center gap-1 mb-3">
              <span className="w-2 h-2 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 bg-accent-blue rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <p className="text-sm text-gray-400">AI is working on the next step...</p>
            <p className="text-xs text-gray-500 mt-1">You'll be asked to approve before any action is taken.</p>
          </div>
        ) : (
          <div className="text-center py-12 text-gray-500">
            <div className="text-3xl mb-2">🎯</div>
            <p className="text-sm">Configure an objective and start autonomous testing.</p>
            <p className="text-xs mt-2 text-gray-600">
              The AI will propose each step and wait for your explicit approval before executing any tools.
              You maintain full control at all times.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
