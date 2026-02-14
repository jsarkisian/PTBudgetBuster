import React from 'react';

export default function Header({ health, connected, session }) {
  return (
    <header className="h-12 bg-dark-900 border-b border-dark-600 flex items-center px-4 justify-between shrink-0">
      <div className="flex items-center gap-3">
        <span className="text-lg">🛡️</span>
        <h1 className="text-sm font-bold text-gray-100 tracking-wide">PentestMCP</h1>
        {session && (
          <>
            <span className="text-dark-400">/</span>
            <span className="text-sm text-accent-cyan font-medium">{session.name}</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-4 text-xs">
        <StatusDot
          ok={health?.ai_configured}
          label="AI"
        />
        <StatusDot
          ok={health?.toolbox === 'connected'}
          label="Toolbox"
        />
        <StatusDot
          ok={connected}
          label="WS"
        />
      </div>
    </header>
  );
}

function StatusDot({ ok, label }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-2 h-2 rounded-full ${ok ? 'bg-accent-green' : 'bg-dark-400'}`} />
      <span className="text-gray-400">{label}</span>
    </div>
  );
}
