import React from 'react';

export default function HomePage({ sessions, currentUser, logoUrl, onNewSession, onSelectSession, onGoToAdmin, onGoToSettings }) {
  const recentSessions = [...sessions]
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 5);

  const totalFindings = sessions.reduce((sum, s) => sum + (s.findings?.length || 0), 0);

  return (
    <div className="flex-1 overflow-y-auto bg-dark-950">
      {/* Hero */}
      <div className="flex flex-col items-center justify-center pt-16 pb-10 px-6">
        {logoUrl
          ? <img src={logoUrl} alt="Logo" className="h-36 w-36 object-contain mb-4 rounded-xl" />
          : <div className="text-7xl mb-4">🛡️</div>
        }
        <h1 className="text-3xl font-bold text-gray-100 tracking-tight mb-2">MCP-PT</h1>
        <p className="text-gray-500 text-sm">AI-powered penetration testing platform</p>
      </div>

      {/* Stats */}
      <div className="max-w-2xl mx-auto px-6 mb-8">
        <div className="grid grid-cols-2 gap-4">
          <StatCard label="Engagements" value={sessions.length} icon="📋" />
          <StatCard label="Findings Logged" value={totalFindings} icon="🔍" />
        </div>
      </div>

      {/* Quick Actions */}
      <div className="max-w-2xl mx-auto px-6 mb-8 flex gap-3">
        <button
          onClick={onNewSession}
          className="btn-primary flex-1 py-2.5"
        >
          + New Engagement
        </button>
        <button
          onClick={onGoToAdmin}
          className="px-5 py-2.5 text-sm bg-dark-700 hover:bg-dark-600 text-gray-300 rounded border border-dark-500 transition-colors"
        >
          {currentUser?.role === 'admin' ? '👥 Users' : '👤 Account'}
        </button>
        {currentUser?.role === 'admin' && (
          <button
            onClick={onGoToSettings}
            className="px-5 py-2.5 text-sm bg-dark-700 hover:bg-dark-600 text-gray-300 rounded border border-dark-500 transition-colors"
          >
            ⚙️ Settings
          </button>
        )}
      </div>

      {/* Recent Engagements */}
      {recentSessions.length > 0 && (
        <div className="max-w-2xl mx-auto px-6 pb-16">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Recent Engagements
          </h2>
          <div className="space-y-2">
            {recentSessions.map(session => (
              <button
                key={session.id}
                onClick={() => onSelectSession(session)}
                className="w-full text-left bg-dark-800 hover:bg-dark-700 border border-dark-600 hover:border-dark-500 rounded-lg px-4 py-3 transition-colors group"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-200 group-hover:text-white transition-colors">
                    {session.name}
                  </span>
                  <span className="text-xs text-gray-600">
                    {new Date(session.created_at).toLocaleDateString()}
                  </span>
                </div>
                {session.target_scope?.length > 0 && (
                  <p className="text-xs text-gray-500 mt-1 truncate">
                    {session.target_scope.join(', ')}
                  </p>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, icon }) {
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-lg px-5 py-4 flex items-center gap-4">
      <span className="text-2xl">{icon}</span>
      <div>
        <div className="text-2xl font-bold text-gray-100">{value}</div>
        <div className="text-xs text-gray-500">{label}</div>
      </div>
    </div>
  );
}
