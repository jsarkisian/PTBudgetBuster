import React, { useState } from 'react';
import { api } from '../utils/api';

function DeleteConfirmModal({ sessionName, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onCancel}>
      <div className="bg-dark-800 border border-dark-500 rounded-lg p-5 max-w-sm mx-4 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="text-lg font-semibold text-gray-200 mb-2">Delete Engagement?</div>
        <p className="text-sm text-gray-400 mb-1">
          Are you sure you want to delete <span className="text-gray-200 font-medium">"{sessionName}"</span>?
        </p>
        <p className="text-sm text-accent-red/80 mb-4">
          This will permanently delete all chat history, tool output, findings, and screenshots associated with this engagement.
        </p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-300 bg-dark-700 hover:bg-dark-600 rounded border border-dark-500 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm text-white bg-red-600 hover:bg-red-500 rounded transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SessionSidebar({ sessions, activeSession, onSelect, onDelete, onNew, onEdit }) {
  const [deleteTarget, setDeleteTarget] = useState(null);

  const handleConfirmDelete = () => {
    if (deleteTarget) {
      onDelete(deleteTarget.id);
      setDeleteTarget(null);
    }
  };

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
                <div className="hidden group-hover:flex items-center gap-2">
                  <button
                    onClick={(e) => { e.stopPropagation(); api.exportSession(session.id); }}
                    className="text-gray-400 hover:text-accent-blue text-base p-0.5 transition-colors"
                    title="Export engagement"
                  >
                    ⬇
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); onEdit(session); }}
                    className="text-gray-400 hover:text-accent-cyan text-base p-0.5 transition-colors"
                    title="Edit engagement"
                  >
                    ✎
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteTarget(session); }}
                    className="text-gray-400 hover:text-accent-red text-base p-0.5 transition-colors"
                    title="Delete engagement"
                  >
                    ✕
                  </button>
                </div>
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

      {deleteTarget && (
        <DeleteConfirmModal
          sessionName={deleteTarget.name}
          onConfirm={handleConfirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
