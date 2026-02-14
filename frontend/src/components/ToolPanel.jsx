import React, { useState } from 'react';

export default function ToolPanel({ tools, onExecute, onBash, loading }) {
  const [selectedTool, setSelectedTool] = useState('');
  const [params, setParams] = useState({});
  const [bashCmd, setBashCmd] = useState('');
  const [mode, setMode] = useState('tool'); // tool | bash

  const toolDef = tools[selectedTool];

  const handleExecute = async () => {
    if (mode === 'bash') {
      if (!bashCmd.trim()) return;
      await onBash(bashCmd.trim());
    } else {
      if (!selectedTool) return;
      await onExecute(selectedTool, params);
    }
  };

  const handleToolChange = (toolName) => {
    setSelectedTool(toolName);
    setParams({});
  };

  const handleParamChange = (key, value) => {
    setParams(prev => ({ ...prev, [key]: value }));
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

                {/* Parameters */}
                <div className="space-y-3">
                  {Object.entries(toolDef.parameters || {}).map(([key, pDef]) => (
                    <div key={key}>
                      <label className="flex items-center gap-2 text-xs text-gray-400 mb-1">
                        <span className="font-mono">{key}</span>
                        {pDef.required && <span className="text-accent-red">*</span>}
                        <span className="text-gray-600">({pDef.type})</span>
                      </label>
                      {pDef.type === 'boolean' ? (
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={!!params[key]}
                            onChange={(e) => handleParamChange(key, e.target.checked)}
                            className="rounded bg-dark-700 border-dark-500"
                          />
                          <span className="text-gray-300 text-xs">{pDef.description}</span>
                        </label>
                      ) : (
                        <input
                          type={pDef.type === 'integer' ? 'number' : 'text'}
                          value={params[key] || ''}
                          onChange={(e) => handleParamChange(key, pDef.type === 'integer' ? parseInt(e.target.value) || '' : e.target.value)}
                          placeholder={pDef.description}
                          className="input text-xs"
                        />
                      )}
                    </div>
                  ))}
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
