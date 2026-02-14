import React from 'react';

export default function SessionSidebar({ sessions, activeSession, onSelect, onDelete, onNew }) {
  return (
    <div className="w-56 bg-dark-900 border-r border-dark-600 flex flex-col shrink-0">
      <div className="p-3 border-b border-dark-600">
        <button onClick={onNew} className="btn-primary w-full text-sm">
          + New Engagement
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <div className="p-4 text-xs text-gray-500 text-center">No engagements yet</div>
        ) : (
          sessions.map(session => (
            <div
              key={session.id}
              onClick={() => onSelect(session)}
              className={`group px-3 py-2.5 cursor-pointer border-b border-dark-700 transition-colors ${
                activeSession?.id === session.id
                  ? 'bg-dark-700 border-l-2 border-l-accent-blue'
                  : 'hover:bg-dark-800 border-l-2 border-l-transparent'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-200 truncate">{session.name}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
                  className="hidden group-hover:block text-gray-500 hover:text-accent-red text-xs"
                  title="Delete"
                >
                  ✕
                </button>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs text-gray-500">{session.target_scope?.[0] || 'No scope'}</span>
                {session.finding_count > 0 && (
                  <span className="badge-high text-[10px] px-1">{session.finding_count}</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
