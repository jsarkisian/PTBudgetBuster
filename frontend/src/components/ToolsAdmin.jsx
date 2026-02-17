import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

export default function ToolsAdmin() {
  const [tools, setTools] = useState({});
  const [selectedTool, setSelectedTool] = useState(null);
  const [showAddTool, setShowAddTool] = useState(false);
  const [showInstallGo, setShowInstallGo] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [updating, setUpdating] = useState(null);

  useEffect(() => { loadTools(); }, []);

  const loadTools = async () => {
    try {
      const data = await api.getToolDefinitions();
      setTools(data.tools || {});
    } catch (err) { setError(err.message); }
  };

  const flash = (msg) => { setSuccess(msg); setTimeout(() => setSuccess(''), 3000); };

  const handleUpdate = async (toolName) => {
    setUpdating(toolName);
    setError('');
    try {
      const result = await api.updateTool(toolName);
      if (result.status === 'updated') flash(`${toolName} updated successfully`);
      else if (result.status === 'skipped') flash(result.message);
      else setError(`Update failed: ${result.error || 'Unknown error'}`);
    } catch (err) { setError(err.message); }
    finally { setUpdating(null); }
  };

  const handleDelete = async (toolName) => {
    if (!confirm(`Delete tool definition for "${toolName}"?`)) return;
    try {
      await api.deleteToolDefinition(toolName);
      flash(`${toolName} removed`);
      if (selectedTool === toolName) setSelectedTool(null);
      loadTools();
    } catch (err) { setError(err.message); }
  };

  const categories = {};
  Object.entries(tools).forEach(([name, def]) => {
    const cat = def.category || 'other';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push({ name, ...def });
  });

  const catLabels = {
    reconnaissance: '🔍 Reconnaissance',
    discovery: '📂 Discovery',
    vulnerability_scanning: '🎯 Vuln Scanning',
    exploitation: '💥 Exploitation',
    other: '🔧 Other',
  };

  return (
    <div className="h-full flex flex-col">
      <div className="panel-header">
        <span className="text-sm font-semibold text-gray-300">Tool Management</span>
        <div className="flex gap-2">
          <button onClick={() => setShowInstallGo(true)} className="text-xs px-3 py-1 bg-dark-700 hover:bg-dark-600 text-gray-300 rounded border border-dark-500 transition-colors">
            Install Tool
          </button>
          <button onClick={() => setShowAddTool(true)} className="btn-primary text-xs px-3 py-1">
            + Add Tool
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-3 mt-2 bg-red-500/10 border border-red-500/30 rounded px-3 py-2 text-xs text-red-400">
          {error} <button onClick={() => setError('')} className="ml-2">✕</button>
        </div>
      )}
      {success && (
        <div className="mx-3 mt-2 bg-green-500/10 border border-green-500/30 rounded px-3 py-2 text-xs text-green-400">{success}</div>
      )}

      <div className="flex-1 flex overflow-hidden">
        <div className="w-72 border-r border-dark-600 overflow-y-auto">
          {Object.entries(catLabels).map(([cat, label]) => {
            const catTools = categories[cat];
            if (!catTools || catTools.length === 0) return null;
            return (
              <div key={cat}>
                <div className="px-3 py-2 text-xs font-semibold text-gray-500 bg-dark-900 border-b border-dark-700">
                  {label}
                </div>
                {catTools.map(tool => (
                  <div
                    key={tool.name}
                    onClick={() => setSelectedTool(tool.name)}
                    className={`px-4 py-2 cursor-pointer border-b border-dark-700 transition-colors flex items-center justify-between ${
                      selectedTool === tool.name ? 'bg-dark-700' : 'hover:bg-dark-800'
                    }`}
                  >
                    <div>
                      <div className="text-sm text-gray-200">{tool.name}</div>
                      <div className="text-[10px] text-gray-500 truncate max-w-[180px]">{tool.description}</div>
                    </div>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded ${
                      tool.risk_level === 'high' ? 'bg-red-500/20 text-red-400' :
                      tool.risk_level === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-green-500/20 text-green-400'
                    }`}>
                      {tool.risk_level || 'low'}
                    </span>
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {selectedTool && tools[selectedTool] ? (
            <ToolDetail
              name={selectedTool}
              def={tools[selectedTool]}
              onUpdate={() => handleUpdate(selectedTool)}
              onDelete={() => handleDelete(selectedTool)}
              onSave={(data) => {
                api.updateToolDefinition(selectedTool, data).then(() => { flash('Saved'); loadTools(); }).catch(e => setError(e.message));
              }}
              updating={updating === selectedTool}
            />
          ) : (
            <div className="text-center text-gray-500 text-sm py-12">
              Select a tool to view details, or add a new one
            </div>
          )}
        </div>
      </div>

      {showAddTool && <AddToolModal onClose={() => setShowAddTool(false)} onAdd={() => { loadTools(); setShowAddTool(false); flash('Tool added'); }} onError={setError} />}
      {showInstallGo && <InstallToolModal onClose={() => setShowInstallGo(false)} onInstalled={(msg) => { setShowInstallGo(false); flash(msg); }} onError={setError} />}
    </div>
  );
}

function ToolDetail({ name, def, onUpdate, onDelete, onSave, updating }) {
  const [editing, setEditing] = useState(false);
  const [desc, setDesc] = useState(def.description || '');
  const [binary, setBinary] = useState(def.binary || '');
  const [category, setCategory] = useState(def.category || 'other');
  const [riskLevel, setRiskLevel] = useState(def.risk_level || 'low');

  useEffect(() => {
    setDesc(def.description || '');
    setBinary(def.binary || '');
    setCategory(def.category || 'other');
    setRiskLevel(def.risk_level || 'low');

  }, [name, def]);

  const handleSave = () => {
    onSave({ ...def, description: desc, binary, category, risk_level: riskLevel });
    setEditing(false);
  };

  const isGoTool = (def.binary || '').startsWith('/root/go/bin/');

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">{name}</h2>
          <p className="text-sm text-gray-400 mt-0.5">{def.description}</p>
        </div>
        <div className="flex items-center gap-2">
          {isGoTool && (
            <button
              onClick={onUpdate}
              disabled={updating}
              className="text-xs px-3 py-1.5 rounded border border-accent-blue/30 text-accent-blue hover:bg-accent-blue/10 transition-colors disabled:opacity-50"
            >
              {updating ? '⟳ Updating...' : '⟳ Update'}
            </button>
          )}
          <button onClick={() => setEditing(!editing)} className="text-xs px-3 py-1.5 rounded border border-dark-500 text-gray-400 hover:text-gray-200 transition-colors">
            {editing ? 'Cancel' : '✎ Edit'}
          </button>
          <button onClick={onDelete} className="text-xs px-3 py-1.5 rounded border border-accent-red/30 text-accent-red hover:bg-accent-red/10 transition-colors">
            Delete
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-dark-800 border border-dark-600 rounded p-3">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Binary</div>
          {editing ? (
            <input value={binary} onChange={e => setBinary(e.target.value)} className="w-full px-2 py-1 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 font-mono focus:outline-none focus:border-accent-blue" />
          ) : (
            <div className="text-sm text-gray-200 font-mono">{def.binary || name}</div>
          )}
        </div>

        <div className="bg-dark-800 border border-dark-600 rounded p-3">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Category</div>
          {editing ? (
            <select value={category} onChange={e => setCategory(e.target.value)} className="w-full px-2 py-1 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:outline-none">
              <option value="reconnaissance">Reconnaissance</option>
              <option value="discovery">Discovery</option>
              <option value="vulnerability_scanning">Vuln Scanning</option>
              <option value="exploitation">Exploitation</option>
              <option value="other">Other</option>
            </select>
          ) : (
            <div className="text-sm text-gray-200">{def.category || 'other'}</div>
          )}
        </div>
        <div className="bg-dark-800 border border-dark-600 rounded p-3">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Risk Level</div>
          {editing ? (
            <select value={riskLevel} onChange={e => setRiskLevel(e.target.value)} className="w-full px-2 py-1 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:outline-none">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          ) : (
            <div className="text-sm text-gray-200">{def.risk_level || 'low'}</div>
          )}
        </div>
      </div>

      {editing && (
        <div>
          <label className="block text-xs text-gray-400 mb-1">Description</label>
          <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2} className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:outline-none focus:border-accent-blue resize-none" />
          <button onClick={handleSave} className="btn-primary text-xs px-4 py-1.5 mt-2">Save Changes</button>
        </div>
      )}

      {def.parameters && Object.keys(def.parameters).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 mb-2">Parameters</h3>
          <div className="bg-dark-800 border border-dark-600 rounded overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-dark-600 text-gray-500">
                  <th className="text-left px-3 py-2">Name</th>
                  <th className="text-left px-3 py-2">Flag</th>
                  <th className="text-left px-3 py-2">Type</th>
                  <th className="text-left px-3 py-2">Required</th>
                  <th className="text-left px-3 py-2">Description</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(def.parameters).map(([pname, pdef]) => (
                  <tr key={pname} className="border-b border-dark-700">
                    <td className="px-3 py-1.5 text-accent-cyan font-mono">{pname}</td>
                    <td className="px-3 py-1.5 text-gray-400 font-mono">{pdef.flag || '-'}</td>
                    <td className="px-3 py-1.5 text-gray-400">{pdef.type}</td>
                    <td className="px-3 py-1.5">{pdef.required ? '✓' : ''}</td>
                    <td className="px-3 py-1.5 text-gray-400">{pdef.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {def.default_args && def.default_args.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 mb-1">Default Arguments</h3>
          <div className="text-sm text-gray-400 font-mono bg-dark-800 border border-dark-600 rounded px-3 py-2">
            {def.default_args.join(' ')}
          </div>
        </div>
      )}
    </div>
  );
}

function AddToolModal({ onClose, onAdd, onError }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [binary, setBinary] = useState('');
  const [category, setCategory] = useState('reconnaissance');
  const [riskLevel, setRiskLevel] = useState('low');

  const handleAdd = async () => {
    if (!name.trim() || !binary.trim()) { onError('Name and binary path required'); return; }
    try {
      await api.addToolDefinition({
        name: name.trim(),
        description: description.trim(),
        binary: binary.trim(),
        category, risk_level: riskLevel,
        default_args: [], parameters: {},
      });
      onAdd();
    } catch (err) { onError(err.message); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-dark-800 border border-dark-500 rounded-lg p-6 w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Add Tool Definition</h2>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Tool Name *</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g., mytool" className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:outline-none focus:border-accent-blue" autoFocus />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Binary Path *</label>
            <input value={binary} onChange={e => setBinary(e.target.value)} placeholder="e.g., /usr/bin/mytool" className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 font-mono focus:outline-none focus:border-accent-blue" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Description</label>
            <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2} className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:outline-none focus:border-accent-blue resize-none" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Category</label>
              <select value={category} onChange={e => setCategory(e.target.value)} className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200">
                <option value="reconnaissance">Reconnaissance</option>
                <option value="discovery">Discovery</option>
                <option value="vulnerability_scanning">Vuln Scanning</option>
                <option value="exploitation">Exploitation</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Risk Level</label>
              <select value={riskLevel} onChange={e => setRiskLevel(e.target.value)} className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-300 bg-dark-700 hover:bg-dark-600 rounded border border-dark-500">Cancel</button>
          <button onClick={handleAdd} className="px-4 py-2 text-sm text-white bg-accent-blue hover:bg-blue-500 rounded">Add Tool</button>
        </div>
      </div>
    </div>
  );
}

function InstallToolModal({ onClose, onInstalled, onError }) {
  const [method, setMethod] = useState('go');
  const [pkg, setPkg] = useState('');
  const [gitRepo, setGitRepo] = useState('');
  const [gitCmd, setGitCmd] = useState('');
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState('');

  const handleInstall = async () => {
    setLoading(true);
    setOutput('');
    try {
      let result;
      if (method === 'go') {
        result = await api.installGoTool(pkg.trim());
      } else if (method === 'apt') {
        result = await api.installAptTool(pkg.trim());
      } else if (method === 'pip') {
        result = await api.installPipTool(pkg.trim());
      } else if (method === 'git') {
        result = await api.installGitTool(gitRepo.trim(), gitCmd.trim());
      }
      if (result.status === 'installed') {
        onInstalled(`Installed successfully${result.binary ? ` → ${result.binary}` : result.path ? ` → ${result.path}` : ''}`);
      } else if (result.status === 'partial') {
        setOutput(result.message);
      } else {
        setOutput(`Failed: ${result.error || 'Unknown error'}`);
      }
    } catch (err) { setOutput(`Error: ${err.message}`); }
    finally { setLoading(false); }
  };

  const placeholders = {
    go: 'github.com/author/tool@latest',
    apt: 'package-name',
    pip: 'package-name',
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-dark-800 border border-dark-500 rounded-lg p-6 w-full max-w-lg mx-4" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Install Tool</h2>

        <div className="flex gap-1 mb-4 bg-dark-900 rounded p-1">
          {[
            { id: 'apt', label: '📦 APT', desc: 'Debian/Kali packages' },
            { id: 'go', label: '🐹 Go', desc: 'Go modules' },
            { id: 'pip', label: '🐍 Pip', desc: 'Python packages' },
            { id: 'git', label: '📁 Git', desc: 'Clone repository' },
          ].map(m => (
            <button
              key={m.id}
              onClick={() => setMethod(m.id)}
              className={`flex-1 px-3 py-2 rounded text-xs transition-colors ${
                method === m.id
                  ? 'bg-accent-blue text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              <div className="font-medium">{m.label}</div>
              <div className="text-[9px] opacity-70">{m.desc}</div>
            </button>
          ))}
        </div>

        <div className="space-y-3">
          {method !== 'git' ? (
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                {method === 'go' ? 'Go Package Path' : method === 'apt' ? 'APT Package Name' : 'Pip Package Name'}
              </label>
              <input
                value={pkg} onChange={e => setPkg(e.target.value)}
                placeholder={placeholders[method]}
                className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 font-mono focus:outline-none focus:border-accent-blue"
                autoFocus
              />
            </div>
          ) : (
            <>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Git Repository URL</label>
                <input
                  value={gitRepo} onChange={e => setGitRepo(e.target.value)}
                  placeholder="https://github.com/author/tool.git"
                  className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 font-mono focus:outline-none focus:border-accent-blue"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Install Command <span className="text-gray-600">(optional, runs in cloned dir)</span></label>
                <input
                  value={gitCmd} onChange={e => setGitCmd(e.target.value)}
                  placeholder="pip3 install . --break-system-packages"
                  className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 font-mono focus:outline-none focus:border-accent-blue"
                />
              </div>
            </>
          )}
        </div>

        {output && (
          <pre className="mt-3 p-2 bg-dark-900 border border-dark-600 rounded text-xs text-gray-400 max-h-32 overflow-auto">
            {output}
          </pre>
        )}

        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-300 bg-dark-700 hover:bg-dark-600 rounded border border-dark-500">
            {output ? 'Close' : 'Cancel'}
          </button>
          <button
            onClick={handleInstall}
            disabled={loading || (method !== 'git' ? !pkg.trim() : !gitRepo.trim())}
            className="px-4 py-2 text-sm text-white bg-accent-blue hover:bg-blue-500 rounded disabled:opacity-50"
          >
            {loading ? '⟳ Installing...' : 'Install'}
          </button>
        </div>
      </div>
    </div>
  );
}
