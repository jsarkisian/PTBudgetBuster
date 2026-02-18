import React from 'react';

export default function Header({ health, connected, session, currentUser, onLogout, logoUrl, onLogoClick }) {
  return (
    <header className="h-12 bg-dark-900 border-b border-dark-600 flex items-center px-4 justify-between shrink-0">
      <div className="flex items-center gap-3">
        <button
          onClick={onLogoClick}
          className="flex items-center gap-3 hover:opacity-80 transition-opacity focus:outline-none"
          title="Go to home"
        >
          {logoUrl
            ? <img src={logoUrl} alt="Logo" className="h-7 w-7 object-contain rounded" />
            : <span className="text-lg">🛡️</span>
          }
          <h1 className="text-sm font-bold text-gray-100 tracking-wide">PentestMCP</h1>
        </button>
        {session && (
          <>
            <span className="text-dark-400">/</span>
            <span className="text-sm text-accent-cyan font-medium">{session.name}</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-4 text-xs">
        <StatusDot ok={health?.ai_configured} label="AI" />
        <StatusDot ok={health?.toolbox === 'connected'} label="Toolbox" />
        <StatusDot ok={connected} label="WS" />
        {currentUser && (
          <div className="flex items-center gap-2 ml-2 pl-2 border-l border-dark-600">
            <span className="text-gray-400">
              {currentUser.display_name || currentUser.username}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
              currentUser.role === 'admin' ? 'bg-accent-red/20 text-accent-red' :
              currentUser.role === 'operator' ? 'bg-accent-blue/20 text-accent-blue' :
              'bg-gray-600/20 text-gray-400'
            }`}>
              {currentUser.role}
            </span>
            <button
              onClick={onLogout}
              className="text-gray-500 hover:text-gray-300 transition-colors ml-1"
              title="Sign out"
            >
              ⏻
            </button>
          </div>
        )}
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
