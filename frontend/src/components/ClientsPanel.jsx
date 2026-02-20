import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

function detectAssetType(value) {
  if (!value) return 'other';
  if (/^https?:\/\//i.test(value)) return 'url';
  if (value.startsWith('*.')) return 'wildcard';
  if (/\/\d+$/.test(value)) return 'cidr';
  if (/^[\d.]+$/.test(value)) return 'ip';
  if (/^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(value)) return 'domain';
  return 'other';
}

const ASSET_TYPE_COLORS = {
  domain: 'text-accent-blue',
  ip: 'text-accent-green',
  cidr: 'text-accent-cyan',
  url: 'text-accent-purple',
  wildcard: 'text-accent-yellow',
  other: 'text-gray-400',
};

export default function ClientsPanel({ onClientsChange }) {
  const [clients, setClients] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);

  // Create client form
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [creating, setCreating] = useState(false);

  // Asset form
  const [showAddAsset, setShowAddAsset] = useState(false);
  const [assetValue, setAssetValue] = useState('');
  const [assetLabel, setAssetLabel] = useState('');
  const [addingAsset, setAddingAsset] = useState(false);

  // Contact form
  const [showAddContact, setShowAddContact] = useState(false);
  const [contactName, setContactName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactRole, setContactRole] = useState('');

  const loadClients = async () => {
    setLoading(true);
    try {
      const data = await api.listClients();
      setClients(data);
      if (onClientsChange) onClientsChange(data);
    } catch (e) {
      console.error('Failed to load clients:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadClients(); }, []);

  const selected = clients.find(c => c.id === selectedId);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const c = await api.createClient({ name: newName.trim(), notes: newNotes.trim() });
      const updated = [...clients, c];
      setClients(updated);
      if (onClientsChange) onClientsChange(updated);
      setSelectedId(c.id);
      setShowCreate(false);
      setNewName(''); setNewNotes('');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this client?')) return;
    await api.deleteClient(id);
    const updated = clients.filter(c => c.id !== id);
    setClients(updated);
    if (onClientsChange) onClientsChange(updated);
    if (selectedId === id) setSelectedId(null);
  };

  const handleAddAsset = async () => {
    if (!assetValue.trim() || !selectedId) return;
    setAddingAsset(true);
    try {
      const asset = await api.addAsset(selectedId, {
        value: assetValue.trim(),
        asset_type: detectAssetType(assetValue.trim()),
        label: assetLabel.trim(),
      });
      setClients(prev => prev.map(c =>
        c.id === selectedId ? { ...c, assets: [...(c.assets || []), asset] } : c
      ));
      setAssetValue(''); setAssetLabel(''); setShowAddAsset(false);
    } finally {
      setAddingAsset(false);
    }
  };

  const handleRemoveAsset = async (assetId) => {
    await api.removeAsset(selectedId, assetId);
    setClients(prev => prev.map(c =>
      c.id === selectedId ? { ...c, assets: c.assets.filter(a => a.id !== assetId) } : c
    ));
  };

  const handleAddContact = async () => {
    if (!contactName.trim() || !selectedId) return;
    const client = clients.find(c => c.id === selectedId);
    if (!client) return;
    const newContact = {
      name: contactName.trim(),
      email: contactEmail.trim(),
      phone: contactPhone.trim(),
      role: contactRole.trim(),
    };
    const updated = await api.updateClient(selectedId, {
      contacts: [...(client.contacts || []), newContact],
    });
    setClients(prev => prev.map(c => c.id === selectedId ? { ...c, contacts: updated.contacts } : c));
    setContactName(''); setContactEmail(''); setContactPhone(''); setContactRole('');
    setShowAddContact(false);
  };

  const handleRemoveContact = async (idx) => {
    const client = clients.find(c => c.id === selectedId);
    if (!client) return;
    const newContacts = client.contacts.filter((_, i) => i !== idx);
    await api.updateClient(selectedId, { contacts: newContacts });
    setClients(prev => prev.map(c => c.id === selectedId ? { ...c, contacts: newContacts } : c));
  };

  return (
    <div className="h-full flex">
      {/* Left: client list */}
      <div className="w-64 border-r border-dark-600 bg-dark-900 flex flex-col shrink-0">
        <div className="p-3 border-b border-dark-600 flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-300 flex-1">Clients</span>
          <button onClick={() => setShowCreate(true)} className="btn-primary text-xs px-2 py-1">+ New</button>
        </div>

        {showCreate && (
          <div className="p-3 border-b border-dark-600 bg-dark-800 space-y-2">
            <input
              type="text"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder="Client name"
              className="input text-xs w-full"
              autoFocus
            />
            <textarea
              value={newNotes}
              onChange={e => setNewNotes(e.target.value)}
              placeholder="Notes (optional)"
              className="input text-xs w-full"
              rows={2}
            />
            <div className="flex gap-2">
              <button onClick={() => setShowCreate(false)} className="btn-ghost text-xs flex-1">Cancel</button>
              <button onClick={handleCreate} disabled={!newName.trim() || creating} className="btn-primary text-xs flex-1">
                {creating ? '...' : 'Create'}
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-xs text-gray-500 text-center">Loading...</div>
          ) : clients.length === 0 ? (
            <div className="p-4 text-xs text-gray-500 text-center">No clients yet</div>
          ) : (
            clients.map(c => (
              <div
                key={c.id}
                onClick={() => setSelectedId(c.id)}
                className={`group px-3 py-2.5 cursor-pointer border-b border-dark-700 transition-colors ${
                  selectedId === c.id
                    ? 'bg-dark-700 border-l-2 border-l-accent-blue'
                    : 'hover:bg-dark-800 border-l-2 border-l-transparent'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-200 truncate">{c.name}</span>
                  <button
                    onClick={e => { e.stopPropagation(); handleDelete(c.id); }}
                    className="hidden group-hover:block text-gray-500 hover:text-accent-red text-xs px-1"
                  >
                    ✕
                  </button>
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {(c.assets || []).length} assets · {(c.contacts || []).length} contacts
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right: client detail */}
      <div className="flex-1 overflow-y-auto p-4 bg-dark-950">
        {!selected ? (
          <div className="h-full flex items-center justify-center text-gray-600 text-sm">
            Select a client to view details
          </div>
        ) : (
          <div className="max-w-2xl space-y-6">
            {/* Header */}
            <div>
              <h2 className="text-xl font-semibold text-gray-200">{selected.name}</h2>
              {selected.notes && (
                <p className="text-sm text-gray-400 mt-1">{selected.notes}</p>
              )}
              <p className="text-xs text-gray-600 mt-1">ID: {selected.id} · Created: {new Date(selected.created_at).toLocaleDateString()}</p>
            </div>

            {/* Contacts */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-300">Contacts</h3>
                <button onClick={() => setShowAddContact(!showAddContact)} className="btn-ghost text-xs px-2 py-1">
                  {showAddContact ? 'Cancel' : '+ Add'}
                </button>
              </div>

              {showAddContact && (
                <div className="bg-dark-800 border border-dark-600 rounded p-3 mb-3 grid grid-cols-2 gap-2">
                  <input value={contactName} onChange={e => setContactName(e.target.value)} placeholder="Name *" className="input text-xs" />
                  <input value={contactRole} onChange={e => setContactRole(e.target.value)} placeholder="Role" className="input text-xs" />
                  <input value={contactEmail} onChange={e => setContactEmail(e.target.value)} placeholder="Email" className="input text-xs" />
                  <input value={contactPhone} onChange={e => setContactPhone(e.target.value)} placeholder="Phone" className="input text-xs" />
                  <div className="col-span-2 flex justify-end">
                    <button onClick={handleAddContact} disabled={!contactName.trim()} className="btn-primary text-xs px-3 py-1">Add</button>
                  </div>
                </div>
              )}

              {(selected.contacts || []).length === 0 ? (
                <p className="text-xs text-gray-600">No contacts</p>
              ) : (
                <div className="space-y-1">
                  {selected.contacts.map((ct, idx) => (
                    <div key={idx} className="flex items-center justify-between bg-dark-800 border border-dark-600 rounded px-3 py-2">
                      <div>
                        <span className="text-sm text-gray-200 font-medium">{ct.name}</span>
                        {ct.role && <span className="text-xs text-gray-500 ml-2">{ct.role}</span>}
                        {ct.email && <span className="text-xs text-gray-400 ml-2">· {ct.email}</span>}
                        {ct.phone && <span className="text-xs text-gray-400 ml-2">· {ct.phone}</span>}
                      </div>
                      <button onClick={() => handleRemoveContact(idx)} className="text-gray-500 hover:text-accent-red text-xs">✕</button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Assets */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-gray-300">Assets</h3>
                <button onClick={() => setShowAddAsset(!showAddAsset)} className="btn-ghost text-xs px-2 py-1">
                  {showAddAsset ? 'Cancel' : '+ Add'}
                </button>
              </div>

              {showAddAsset && (
                <div className="bg-dark-800 border border-dark-600 rounded p-3 mb-3 space-y-2">
                  <div className="flex gap-2">
                    <input
                      value={assetValue}
                      onChange={e => setAssetValue(e.target.value)}
                      placeholder="Value (e.g., example.com, 10.0.0.0/8)"
                      className="input text-xs flex-1"
                      autoFocus
                    />
                    <input
                      value={assetLabel}
                      onChange={e => setAssetLabel(e.target.value)}
                      placeholder="Label (optional)"
                      className="input text-xs w-40"
                    />
                  </div>
                  {assetValue && (
                    <p className="text-xs text-gray-500">Detected type: <span className="text-accent-blue">{detectAssetType(assetValue)}</span></p>
                  )}
                  <div className="flex justify-end">
                    <button onClick={handleAddAsset} disabled={!assetValue.trim() || addingAsset} className="btn-primary text-xs px-3 py-1">
                      {addingAsset ? '...' : 'Add Asset'}
                    </button>
                  </div>
                </div>
              )}

              {(selected.assets || []).length === 0 ? (
                <p className="text-xs text-gray-600">No assets</p>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b border-dark-600">
                      <th className="text-left py-1 pr-3">Value</th>
                      <th className="text-left py-1 pr-3">Type</th>
                      <th className="text-left py-1 pr-3">Label</th>
                      <th className="py-1"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.assets.map(asset => (
                      <tr key={asset.id} className="border-b border-dark-800 hover:bg-dark-800/50">
                        <td className="py-1.5 pr-3 font-mono text-gray-200">{asset.value}</td>
                        <td className={`py-1.5 pr-3 ${ASSET_TYPE_COLORS[asset.asset_type] || 'text-gray-400'}`}>{asset.asset_type}</td>
                        <td className="py-1.5 pr-3 text-gray-400">{asset.label}</td>
                        <td className="py-1.5">
                          <button onClick={() => handleRemoveAsset(asset.id)} className="text-gray-500 hover:text-accent-red">✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            {/* Linked Sessions */}
            {selected.sessions && selected.sessions.length > 0 && (
              <section>
                <h3 className="text-sm font-semibold text-gray-300 mb-2">Linked Sessions</h3>
                <div className="space-y-1">
                  {selected.sessions.map(s => (
                    <div key={s.id} className="text-xs text-gray-400 bg-dark-800 border border-dark-600 rounded px-3 py-2">
                      <span className="text-gray-200">{s.name}</span>
                      <span className="text-gray-600 ml-2">{new Date(s.created_at).toLocaleDateString()}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
