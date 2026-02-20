import React, { useState } from 'react';

export default function NewSessionModal({ onClose, onCreate, clients = [] }) {
  const [name, setName] = useState('');
  const [scope, setScope] = useState('');
  const [notes, setNotes] = useState('');
  const [clientId, setClientId] = useState('');
  const [loading, setLoading] = useState(false);

  const handleClientChange = (id) => {
    setClientId(id);
    if (id) {
      const client = clients.find(c => c.id === id);
      if (client && client.assets && client.assets.length > 0) {
        setScope(client.assets.map(a => a.value).join('\n'));
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    try {
      await onCreate({
        name: name.trim(),
        target_scope: scope.split('\n').map(s => s.trim()).filter(Boolean),
        notes: notes.trim(),
        client_id: clientId || null,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-dark-800 border border-dark-600 rounded-xl w-full max-w-lg mx-4 shadow-2xl">
        <div className="px-6 py-4 border-b border-dark-600 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-200">New Engagement</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200 text-xl">&times;</button>
        </div>
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {clients.length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-1.5 font-medium">Client</label>
              <select
                value={clientId}
                onChange={e => handleClientChange(e.target.value)}
                className="input w-full"
              >
                <option value="">No client</option>
                {clients.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium">
              Engagement Name <span className="text-accent-red">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Acme Corp External Pentest Q1 2026"
              className="input"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium">
              Target Scope <span className="text-gray-500">(one per line)</span>
            </label>
            <textarea
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              placeholder={"example.com\n*.example.com\n203.0.113.0/24"}
              className="input text-xs font-mono min-h-[100px]"
              rows={4}
            />
            <p className="text-xs text-gray-500 mt-1">
              Domains, subdomains, IPs, or CIDR ranges that are in scope for testing.
            </p>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Rules of engagement, testing windows, contacts..."
              className="input text-xs min-h-[80px]"
              rows={3}
            />
          </div>

          <div className="bg-dark-700 border border-dark-500 rounded p-3">
            <div className="flex items-center gap-2 text-xs text-accent-yellow">
              <span>⚠️</span>
              <span className="font-medium">Ethical Testing Reminder</span>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Only test targets you have explicit written authorization to test. 
              All testing activity is logged within this session.
            </p>
          </div>

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim() || loading}
              className="btn-primary flex-1"
            >
              {loading ? 'Creating...' : 'Create Engagement'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
