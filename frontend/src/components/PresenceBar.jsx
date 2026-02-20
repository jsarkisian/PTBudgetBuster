import React from 'react';

const ACCENT_COLORS = [
  '#3b9eff', // accent-blue
  '#00d9a3', // accent-green
  '#22d3ee', // accent-cyan
  '#a78bfa', // accent-purple
  '#f59e0b', // accent-yellow
  '#f87171', // accent-red
];

function hashUsername(username) {
  let hash = 0;
  for (let i = 0; i < username.length; i++) {
    hash = (hash * 31 + username.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function Avatar({ username }) {
  const color = ACCENT_COLORS[hashUsername(username) % ACCENT_COLORS.length];
  const initials = username.slice(0, 2).toUpperCase();
  return (
    <div
      title={username}
      style={{ backgroundColor: color + '33', border: `1.5px solid ${color}`, color }}
      className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold shrink-0"
    >
      {initials}
    </div>
  );
}

export default function PresenceBar({ users }) {
  if (!users || users.length <= 1) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-1.5 bg-dark-900 border-b border-dark-600 text-xs text-gray-400">
      <span className="shrink-0">Online:</span>
      <div className="flex items-center gap-1">
        {users.map((u, i) => (
          <Avatar key={i} username={u.username} />
        ))}
      </div>
      <span className="text-gray-600">{users.map(u => u.username).join(', ')}</span>
    </div>
  );
}
