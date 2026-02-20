import React, { useState } from 'react';

export default function ToolPanel({ tools, onExecute, onBash, loading }) {
  const [selectedTool, setSelectedTool] = useState('');
  const [rawArgs, setRawArgs] = useState('');
  const [bashCmd, setBashCmd] = useState('');
  const [mode, setMode] = useState('tool'); // tool | bash

  const toolDef = tools[selectedTool];

  const handleExecute = async () => {
    if (mode === 'bash') {
      if (!bashCmd.trim()) return;
      await onBash(bashCmd.trim());
    } else {
      if (!selectedTool) return;
      await onExecute(selectedTool, { __raw_args__: rawArgs.trim() });
    }
  };

  const handleToolChange = (toolName) => {
    setSelectedTool(toolName);
    setRawArgs('');
  };

  const categories = {};
  Object.entries(tools).forEach(([name, def]) => {
    const cat = def.category || 'other';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push({ name, ...def });
  });

  return (
    <div className="h-full flex flex-col">
      {/* Mode toggle */}
      <div className="flex border-b border-dark-600 bg-dark-800">
        <button
          onClick={() => setMode('tool')}
          className={`flex-1 py-2 text-xs font-medium ${mode === 'tool' ? 'text-accent-blue border-b border-accent-blue' : 'text-gray-400'}`}
        >
          Tool Selector
        </button>
        <button
          onClick={() => setMode('bash')}
          className={`flex-1 py-2 text-xs font-medium ${mode === 'bash' ? 'text-accent-blue border-b border-accent-blue' : 'text-gray-400'}`}
        >
          Bash Command
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {mode === 'bash' ? (
          <div>
            <label className="block text-xs text-gray-400 mb-2 font-medium">Command</label>
            <textarea
              value={bashCmd}
              onChange={(e) => setBashCmd(e.target.value)}
              placeholder="e.g., subfinder -d example.com | httpx -silent | nuclei -severity high"
              className="input font-mono text-xs min-h-[120px]"
              rows={5}
            />
            <p className="text-xs text-gray-500 mt-2">
              Use bash for complex commands, pipes, and tool chaining.
            </p>
          </div>
        ) : (
          <div>
            {/* Tool selector */}
            <label className="block text-xs text-gray-400 mb-2 font-medium">Select Tool</label>
            <select
              value={selectedTool}
              onChange={(e) => handleToolChange(e.target.value)}
              className="input mb-4"
            >
              <option value="">-- Choose a tool --</option>
              {Object.entries(categories).map(([cat, toolList]) => (
                <optgroup key={cat} label={cat.replace('_', ' ').toUpperCase()}>
                  {toolList.map(t => (
                    <option key={t.name} value={t.name}>
                      {t.name} — {t.description?.slice(0, 50)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>

            {toolDef && (
              <div>
                {/* Tool info */}
                <div className="mb-4 p-3 bg-dark-800 rounded border border-dark-600">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-sm text-accent-cyan font-bold">{selectedTool}</span>
                    <RiskBadge level={toolDef.risk_level} />
                  </div>
                  <p className="text-xs text-gray-400">{toolDef.description}</p>
                </div>

                {/* Free-form arguments */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1 font-medium">
                    Arguments
                    <span className="text-gray-600 font-normal ml-2">— type the flags and values exactly as you would on the command line</span>
                  </label>
                  <div className="flex items-start gap-2">
                    <span className="font-mono text-xs text-accent-cyan mt-2 shrink-0">{selectedTool}</span>
                    <textarea
                      value={rawArgs}
                      onChange={e => setRawArgs(e.target.value)}
                      placeholder={buildPlaceholder(toolDef)}
                      className="input font-mono text-xs flex-1 min-h-[72px]"
                      rows={3}
                    />
                  </div>
                  <ParamHints toolDef={toolDef} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Execute button */}
      <div className="p-3 border-t border-dark-600 bg-dark-900">
        <button
          onClick={handleExecute}
          disabled={loading || (mode === 'tool' && !selectedTool) || (mode === 'bash' && !bashCmd.trim())}
          className="btn-success w-full"
        >
          {loading ? 'Executing...' : mode === 'bash' ? 'Run Command' : `Execute ${selectedTool || 'Tool'}`}
        </button>
      </div>
    </div>
  );
}

function RiskBadge({ level }) {
  const colors = {
    low: 'badge-low',
    medium: 'badge-medium',
    high: 'badge-high',
  };
  return <span className={colors[level] || 'badge-info'}>{level}</span>;
}

/** Build a placeholder showing common flags for the selected tool */
function buildPlaceholder(toolDef) {
  if (!toolDef?.parameters) return 'e.g., -u https://example.com';
  const parts = [];
  for (const [, pDef] of Object.entries(toolDef.parameters).slice(0, 3)) {
    if (pDef.flag && pDef.description) {
      parts.push(`${pDef.flag} <${pDef.description.split(' ').slice(0, 2).join('-').toLowerCase()}>`);
    }
  }
  return parts.length ? parts.join(' ') : 'e.g., -u https://example.com';
}

/** Show a collapsed reference list of available flags */
function ParamHints({ toolDef }) {
  const [open, setOpen] = React.useState(false);
  const params = Object.entries(toolDef?.parameters || {});
  if (!params.length) return null;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="text-xs text-gray-600 hover:text-gray-400 underline"
      >
        {open ? 'Hide' : 'Show'} available flags
      </button>
      {open && (
        <div className="mt-1 p-2 bg-dark-900 border border-dark-600 rounded space-y-1">
          {params.map(([name, pDef]) => (
            <div key={name} className="flex gap-2 text-xs">
              <span className="font-mono text-accent-cyan shrink-0 w-24">{pDef.flag || name}</span>
              <span className="text-gray-500">{pDef.description}</span>
              {pDef.required && <span className="text-accent-red shrink-0">required</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
