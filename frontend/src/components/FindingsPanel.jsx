import React, { useState } from 'react';

export default function FindingsPanel({ findings }) {
  const [sortBy, setSortBy] = useState('severity');
  const [expandedId, setExpandedId] = useState(null);

  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

  const sorted = [...findings].sort((a, b) => {
    if (sortBy === 'severity') {
      return (severityOrder[a.severity] ?? 5) - (severityOrder[b.severity] ?? 5);
    }
    return new Date(b.timestamp) - new Date(a.timestamp);
  });

  const counts = findings.reduce((acc, f) => {
    acc[f.severity] = (acc[f.severity] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="h-full flex flex-col">
      {/* Summary */}
      <div className="p-4 border-b border-dark-600 bg-dark-800">
        <div className="flex items-center gap-4 mb-3">
          <h3 className="text-sm font-semibold text-gray-200">Findings Summary</h3>
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            className="text-xs bg-dark-700 border border-dark-500 rounded px-2 py-1 text-gray-300 ml-auto"
          >
            <option value="severity">Sort by Severity</option>
            <option value="time">Sort by Time</option>
          </select>
        </div>
        <div className="flex gap-3">
          {['critical', 'high', 'medium', 'low', 'info'].map(sev => (
            <div key={sev} className="flex items-center gap-1.5">
              <SeverityDot severity={sev} />
              <span className="text-xs text-gray-400 capitalize">{sev}</span>
              <span className="text-xs font-bold text-gray-300">{counts[sev] || 0}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Findings list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {sorted.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <div className="text-3xl mb-2">🔍</div>
            <p className="text-sm">No findings yet. Start testing to discover vulnerabilities.</p>
          </div>
        ) : (
          sorted.map(finding => (
            <div
              key={finding.id}
              className="panel cursor-pointer"
              onClick={() => setExpandedId(expandedId === finding.id ? null : finding.id)}
            >
              <div className="px-4 py-3 flex items-start gap-3">
                <SeverityDot severity={finding.severity} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`badge badge-${finding.severity}`}>
                      {finding.severity.toUpperCase()}
                    </span>
                    <span className="text-sm font-medium text-gray-200 truncate">
                      {finding.title}
                    </span>
                  </div>
                  {expandedId === finding.id && (
                    <div className="mt-3 space-y-3">
                      <div>
                        <div className="text-xs font-medium text-gray-400 mb-1">Description</div>
                        <p className="text-xs text-gray-300 whitespace-pre-wrap">{finding.description}</p>
                      </div>
                      {finding.evidence && (
                        <div>
                          <div className="text-xs font-medium text-gray-400 mb-1">Evidence</div>
                          <pre className="terminal text-gray-400 bg-dark-950 p-2 rounded max-h-48 overflow-auto">
                            {finding.evidence}
                          </pre>
                        </div>
                      )}
                      <div className="text-xs text-gray-500">
                        Discovered: {new Date(finding.timestamp).toLocaleString()}
                      </div>
                    </div>
                  )}
                </div>
                <span className="text-xs text-gray-500">
                  {expandedId === finding.id ? '▼' : '▶'}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function SeverityDot({ severity }) {
  const colors = {
    critical: 'bg-red-500',
    high: 'bg-orange-500',
    medium: 'bg-yellow-500',
    low: 'bg-blue-500',
    info: 'bg-gray-500',
  };
  return <div className={`w-2.5 h-2.5 rounded-full ${colors[severity] || 'bg-gray-500'} mt-1 shrink-0`} />;
}
