import { useState, useEffect } from 'react';
import { api } from '../utils/api';

export default function PlaybookManager() {
  const [playbooks, setPlaybooks] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({
    name: '',
    description: '',
    category: 'general',
    approval_default: 'manual',
    phases: [{ name: '', goal: '', tools_hint: '', max_steps: 2 }],
  });

  const loadPlaybooks = () => {
    api.getPlaybooks().then(setPlaybooks).catch(() => {});
  };

  useEffect(() => { loadPlaybooks(); }, []);

  const resetForm = () => {
    setForm({
      name: '',
      description: '',
      category: 'general',
      approval_default: 'manual',
      phases: [{ name: '', goal: '', tools_hint: '', max_steps: 2 }],
    });
    setEditingId(null);
    setShowForm(false);
  };

  const handleSave = async () => {
    const data = {
      ...form,
      id: form.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
      phases: form.phases.map(p => ({
        ...p,
        tools_hint: typeof p.tools_hint === 'string'
          ? p.tools_hint.split(',').map(t => t.trim()).filter(Boolean)
          : p.tools_hint,
        max_steps: parseInt(p.max_steps) || 2,
      })),
    };

    try {
      if (editingId) {
        await api.updatePlaybook(editingId, data);
      } else {
        await api.createPlaybook(data);
      }
      resetForm();
      loadPlaybooks();
    } catch (e) {
      alert(e.message || 'Failed to save playbook');
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this playbook?')) return;
    try {
      await api.deletePlaybook(id);
      loadPlaybooks();
    } catch (e) {
      alert(e.message || 'Failed to delete');
    }
  };

  const handleEdit = (pb) => {
    setForm({
      name: pb.name,
      description: pb.description,
      category: pb.category,
      approval_default: pb.approval_default,
      phases: pb.phases.map(p => ({
        name: p.name,
        goal: p.goal,
        tools_hint: Array.isArray(p.tools_hint) ? p.tools_hint.join(', ') : p.tools_hint,
        max_steps: p.max_steps,
      })),
    });
    setEditingId(pb.id);
    setShowForm(true);
  };

  const addPhase = () => {
    setForm(f => ({
      ...f,
      phases: [...f.phases, { name: '', goal: '', tools_hint: '', max_steps: 2 }],
    }));
  };

  const removePhase = (idx) => {
    setForm(f => ({
      ...f,
      phases: f.phases.filter((_, i) => i !== idx),
    }));
  };

  const updatePhase = (idx, field, value) => {
    setForm(f => ({
      ...f,
      phases: f.phases.map((p, i) => i === idx ? { ...p, [field]: value } : p),
    }));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">Playbooks</h3>
        {!showForm && (
          <button
            onClick={() => { resetForm(); setShowForm(true); }}
            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
          >
            Create Playbook
          </button>
        )}
      </div>

      {/* Playbook List */}
      {!showForm && (
        <div className="space-y-2">
          {playbooks.map(pb => (
            <div key={pb.id} className="bg-gray-800 rounded p-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-white font-medium">{pb.name}</span>
                  {pb.builtin && (
                    <span className="ml-2 px-1.5 py-0.5 bg-gray-600 text-gray-300 text-xs rounded">
                      Built-in
                    </span>
                  )}
                  <span className="ml-2 px-1.5 py-0.5 bg-gray-700 text-gray-400 text-xs rounded">
                    {pb.category}
                  </span>
                </div>
                {!pb.builtin && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleEdit(pb)}
                      className="text-sm text-blue-400 hover:text-blue-300"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(pb.id)}
                      className="text-sm text-red-400 hover:text-red-300"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
              <p className="text-gray-400 text-sm mt-1">{pb.description}</p>
              <div className="text-gray-500 text-xs mt-1">
                {pb.phases.length} phases &middot; {pb.phases.reduce((s, p) => s + p.max_steps, 0)} total steps &middot; {pb.approval_default === 'auto' ? 'Auto-approve' : 'Manual approval'}
              </div>
            </div>
          ))}
          {playbooks.length === 0 && (
            <p className="text-gray-500 text-sm">No playbooks found.</p>
          )}
        </div>
      )}

      {/* Create/Edit Form */}
      {showForm && (
        <div className="bg-gray-800 rounded p-4 space-y-3">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Name</label>
            <input
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className="w-full bg-gray-700 text-white rounded px-3 py-2 text-sm"
              placeholder="My Custom Playbook"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Description</label>
            <textarea
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full bg-gray-700 text-white rounded px-3 py-2 text-sm"
              rows={2}
              placeholder="What this playbook does..."
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-sm text-gray-400 mb-1">Category</label>
              <select
                value={form.category}
                onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                className="w-full bg-gray-700 text-white rounded px-3 py-2 text-sm"
              >
                <option value="reconnaissance">Reconnaissance</option>
                <option value="web">Web</option>
                <option value="internal">Internal</option>
                <option value="general">General</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-sm text-gray-400 mb-1">Approval Default</label>
              <select
                value={form.approval_default}
                onChange={e => setForm(f => ({ ...f, approval_default: e.target.value }))}
                className="w-full bg-gray-700 text-white rounded px-3 py-2 text-sm"
              >
                <option value="manual">Manual</option>
                <option value="auto">Auto-approve</option>
              </select>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-gray-400">Phases</label>
              <button
                onClick={addPhase}
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                + Add Phase
              </button>
            </div>
            {form.phases.map((phase, idx) => (
              <div key={idx} className="bg-gray-900/50 rounded p-3 mb-2">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-gray-500">Phase {idx + 1}</span>
                  {form.phases.length > 1 && (
                    <button
                      onClick={() => removePhase(idx)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Remove
                    </button>
                  )}
                </div>
                <input
                  value={phase.name}
                  onChange={e => updatePhase(idx, 'name', e.target.value)}
                  className="w-full bg-gray-700 text-white rounded px-2 py-1 text-sm mb-2"
                  placeholder="Phase name"
                />
                <textarea
                  value={phase.goal}
                  onChange={e => updatePhase(idx, 'goal', e.target.value)}
                  className="w-full bg-gray-700 text-white rounded px-2 py-1 text-sm mb-2"
                  rows={2}
                  placeholder="Phase goal — what should the AI accomplish?"
                />
                <div className="flex gap-2">
                  <input
                    value={phase.tools_hint}
                    onChange={e => updatePhase(idx, 'tools_hint', e.target.value)}
                    className="flex-1 bg-gray-700 text-white rounded px-2 py-1 text-sm"
                    placeholder="Suggested tools (comma-separated)"
                  />
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={phase.max_steps}
                    onChange={e => updatePhase(idx, 'max_steps', e.target.value)}
                    className="w-20 bg-gray-700 text-white rounded px-2 py-1 text-sm"
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="flex gap-2 pt-2">
            <button
              onClick={handleSave}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
            >
              {editingId ? 'Update' : 'Create'}
            </button>
            <button
              onClick={resetForm}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
