import React, { useState, useMemo } from 'react';

const ACCENT_COLORS = [
  '#3b9eff', '#00d9a3', '#22d3ee', '#a78bfa', '#f59e0b', '#f87171',
];

function hashUsername(username) {
  let hash = 0;
  for (let i = 0; i < username.length; i++) {
    hash = (hash * 31 + username.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function UserBadge({ username }) {
  if (!username) return (
    <div className="w-5 h-5 rounded-full bg-dark-600 border border-dark-500 flex items-center justify-center text-[9px] text-gray-500 shrink-0">?</div>
  );
  const color = ACCENT_COLORS[hashUsername(username) % ACCENT_COLORS.length];
  return (
    <div
      title={username}
      style={{ backgroundColor: color + '33', border: `1.5px solid ${color}`, color }}
      className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold shrink-0"
    >
      {username.slice(0, 2).toUpperCase()}
    </div>
  );
}

function buildTimeline(session) {
  if (!session) return [];
  const entries = [];

  for (const msg of (session.messages || [])) {
    entries.push({
      ts: msg.timestamp,
      type: 'chat',
      role: msg.role,
      user: msg.user || (msg.role === 'assistant' ? 'AI' : null),
      summary: msg.content ? msg.content.slice(0, 120) : '',
      detail: msg.content,
    });
  }

  for (const evt of (session.events || [])) {
    const tool = evt.data?.tool || evt.data?.command?.slice(0, 40) || evt.type;
    entries.push({
      ts: evt.timestamp,
      type: 'tool',
      eventType: evt.type,
      user: evt.user || null,
      summary: `${evt.type}: ${tool}`,
      detail: JSON.stringify(evt.data, null, 2),
    });
  }

  entries.sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));
  return entries;
}

const PAGE_SIZE = 200;

export default function ActivityLogPanel({ session }) {
  const [filter, setFilter] = useState('all'); // all | chat | tools | <username>
  const [expanded, setExpanded] = useState({});
  const [limit, setLimit] = useState(PAGE_SIZE);

  const allEntries = useMemo(() => buildTimeline(session), [session?.id, session?.messages?.length, session?.events?.length]);

  const users = useMemo(() => {
    const u = new Set();
    for (const e of allEntries) {
      if (e.user && e.user !== 'AI') u.add(e.user);
    }
    return [...u];
  }, [allEntries]);

  const filtered = useMemo(() => {
    if (filter === 'all') return allEntries;
    if (filter === 'chat') return allEntries.filter(e => e.type === 'chat');
    if (filter === 'tools') return allEntries.filter(e => e.type === 'tool');
    return allEntries.filter(e => e.user === filter);
  }, [allEntries, filter]);

  const visible = filtered.slice(Math.max(0, filtered.length - limit));

  const toggleExpand = (idx) => setExpanded(prev => ({ ...prev, [idx]: !prev[idx] }));

  return (
    <div className="h-full flex flex-col">
      <div className="panel-header shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-300">Activity Log</span>
          <span className="text-xs text-gray-500">{filtered.length} entries</span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="text-xs bg-dark-700 border border-dark-500 rounded px-2 py-1 text-gray-300"
          >
            <option value="all">All</option>
            <option value="chat">Chat</option>
            <option value="tools">Tools</option>
            {users.map(u => <option key={u} value={u}>{u}</option>)}
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 bg-dark-950 space-y-1">
        {filtered.length === 0 ? (
          <div className="text-center text-gray-600 text-xs py-8">No activity yet.</div>
        ) : (
          <>
            {filtered.length > limit && (
              <div className="text-center py-2">
                <button onClick={() => setLimit(l => l + PAGE_SIZE)} className="btn-ghost text-xs px-3 py-1">
                  Load older ({filtered.length - limit} more)
                </button>
              </div>
            )}
            {visible.map((entry, i) => {
              const globalIdx = filtered.length - visible.length + i;
              const isExp = expanded[globalIdx];
              return (
                <div key={globalIdx} className="flex gap-2 items-start group">
                  <UserBadge username={entry.user} />
                  <div className="flex-1 min-w-0">
                    <div
                      className="flex items-center gap-2 cursor-pointer"
                      onClick={() => toggleExpand(globalIdx)}
                    >
                      <span className="text-[10px] text-gray-600 shrink-0">
                        {entry.ts ? new Date(entry.ts).toLocaleTimeString() : ''}
                      </span>
                      {entry.type === 'chat' && (
                        <span className={`text-[10px] px-1 rounded shrink-0 ${
                          entry.role === 'assistant' ? 'bg-accent-purple/20 text-accent-purple' :
                          entry.role === 'user' ? 'bg-accent-blue/20 text-accent-blue' :
                          'bg-dark-600 text-gray-500'
                        }`}>
                          {entry.role}
                        </span>
                      )}
                      {entry.type === 'tool' && (
                        <span className="text-[10px] bg-dark-700 text-accent-cyan px-1 rounded shrink-0">{entry.eventType}</span>
                      )}
                      <span className="text-xs text-gray-300 truncate">{entry.summary}</span>
                      {entry.detail && entry.detail.length > 120 && (
                        <span className="text-gray-600 text-[10px] shrink-0">{isExp ? '▼' : '▶'}</span>
                      )}
                    </div>
                    {isExp && entry.detail && (
                      <pre className="mt-1 text-xs text-gray-400 bg-dark-900 rounded p-2 max-h-48 overflow-auto font-mono whitespace-pre-wrap break-words">
                        {entry.detail}
                      </pre>
                    )}
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
