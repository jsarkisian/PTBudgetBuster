import React, { useRef, useEffect, useState } from 'react';
import { Lightbox, ScreenshotThumb, buildImageUrl, extractImagePaths } from './ImageUtils';

export default function OutputPanel({ outputs, onClear }) {
  const scrollRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState('all');
  const [lightbox, setLightbox] = useState(null); // {src, filename}

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [outputs, autoScroll]);

  const filtered = filter === 'all'
    ? outputs
    : outputs.filter(o => o.source === filter || o.type === 'auto_status');

  return (
    <div className="h-full flex flex-col">
      <div className="panel-header shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-300">Output</span>
          <span className="text-xs text-gray-500">{outputs.length} entries</span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="text-xs bg-dark-700 border border-dark-500 rounded px-2 py-1 text-gray-300"
          >
            <option value="all">All</option>
            <option value="manual">Manual</option>
            <option value="ai_agent">AI Agent</option>
            <option value="scheduler">Scheduler</option>
          </select>
          <label className="flex items-center gap-1 text-xs text-gray-400">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={e => setAutoScroll(e.target.checked)}
              className="rounded-sm"
            />
            Auto-scroll
          </label>
          <button onClick={onClear} className="btn-ghost text-xs px-2 py-1">
            Clear
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2 bg-dark-950">
        {filtered.length === 0 ? (
          <div className="text-center text-gray-600 text-xs py-8">
            Tool output will appear here...
          </div>
        ) : (
          filtered.map((entry, i) => (
            <OutputEntry
              key={`${entry.id}-${i}`}
              entry={entry}
              onImageClick={(src, filename) => setLightbox({ src, filename })}
            />
          ))
        )}
      </div>

      {lightbox && (
        <Lightbox src={lightbox.src} filename={lightbox.filename} onClose={() => setLightbox(null)} />
      )}
    </div>
  );
}


function OutputEntry({ entry, onImageClick }) {
  const [expanded, setExpanded] = useState(true);

  if (entry.type === 'auto_status') {
    return (
      <div className="px-3 py-2 bg-accent-purple/10 border border-accent-purple/20 rounded text-xs text-accent-purple">
        🤖 {entry.message}
      </div>
    );
  }

  if (entry.type === 'start') {
    return (
      <div className="px-3 py-2 bg-dark-800 border border-dark-600 rounded">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-accent-yellow">▶</span>
          <span className="font-mono text-accent-cyan font-medium">{entry.tool}</span>
          {entry.source === 'ai_agent' && (
            <span className="text-[10px] bg-accent-purple/20 text-accent-purple px-1.5 rounded">AI</span>
          )}
          {entry.source === 'scheduler' && (
            <span className="text-[10px] bg-accent-yellow/20 text-accent-yellow px-1.5 rounded">SCHED</span>
          )}
          <span className="text-gray-500 ml-auto">
            {new Date(entry.timestamp).toLocaleTimeString()}
          </span>
        </div>
        {entry.parameters && Object.keys(entry.parameters).length > 0 && (
          <div className="mt-1 text-xs text-gray-500 font-mono">
            {Object.entries(entry.parameters).map(([k, v]) => (
              <span key={k} className="mr-2">{k}={JSON.stringify(v)}</span>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (entry.type === 'result') {
    const result = entry.result || {};
    const isSuccess = result.status === 'completed';
    const output = result.output || '';
    const error = result.error || '';
    const command = result.command || '';
    const params = result.parameters || {};

    // Build text to search for image paths — include output, command, and parameter values
    const paramValues = Object.values(params).map(v => String(v)).join('\n');
    const searchText = [output, command, error, paramValues].join('\n');

    // Extract screenshot paths from output and command
    let imagePaths = extractImagePaths(searchText);

    // For screenshot tools, also try to load from the screenshots API
    const isScreenshotTool = entry.tool === 'gowitness' || 
      command.includes('gowitness') || 
      command.includes('screenshot') ||
      paramValues.includes('screenshot');

    const [apiScreenshots, setApiScreenshots] = useState([]);

    useEffect(() => {
      if (isScreenshotTool && isSuccess && imagePaths.length === 0) {
        fetch('/api/screenshots')
          .then(r => r.json())
          .then(data => {
            if (data.screenshots && data.screenshots.length > 0) {
              setApiScreenshots(data.screenshots.map(s => s.path));
            }
          })
          .catch(() => {});
      }
    }, []);

    const allImages = [...new Set([...imagePaths, ...apiScreenshots])];

    return (
      <div className={`border rounded ${
        isSuccess ? 'border-accent-green/30 bg-dark-800' : 'border-accent-red/30 bg-red-500/5'
      }`}>
        <div
          className="flex items-center gap-2 px-3 py-2 cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        >
          <span className={`text-xs ${isSuccess ? 'text-accent-green' : 'text-accent-red'}`}>
            {isSuccess ? '✓' : '✗'}
          </span>
          <span className="font-mono text-xs text-accent-cyan">{entry.tool}</span>
          {entry.source === 'ai_agent' && (
            <span className="text-[10px] bg-accent-purple/20 text-accent-purple px-1.5 rounded">AI</span>
          )}
          {entry.source === 'scheduler' && (
            <span className="text-[10px] bg-accent-yellow/20 text-accent-yellow px-1.5 rounded">SCHED</span>
          )}
          <span className={`text-[10px] ${isSuccess ? 'text-accent-green' : 'text-accent-red'}`}>
            {result.status}
          </span>
          {allImages.length > 0 && (
            <span className="text-[10px] bg-accent-blue/20 text-accent-blue px-1.5 rounded">
              📸 {allImages.length}
            </span>
          )}
          <span className="text-gray-500 text-xs ml-auto">
            {expanded ? '▼' : '▶'}
          </span>
        </div>

        {expanded && (
          <div className="px-3 pb-3 border-t border-dark-600">
            {/* Screenshots */}
            {allImages.length > 0 && (
              <div className="mt-2 mb-2">
                <div className="text-xs text-gray-400 font-medium mb-1.5">Screenshots</div>
                <div className="flex flex-wrap gap-2">
                  {allImages.map((imgPath, idx) => (
                    <ScreenshotThumb
                      key={idx}
                      path={imgPath}
                      onClick={onImageClick}
                    />
                  ))}
                </div>
              </div>
            )}

            {output && (
              <pre className="terminal mt-2 text-gray-300 max-h-64 overflow-auto bg-dark-950 p-2 rounded">
                {output}
              </pre>
            )}
            {error && (
              <pre className="terminal mt-2 text-red-400 max-h-32 overflow-auto bg-dark-950 p-2 rounded">
                {error}
              </pre>
            )}
          </div>
        )}
      </div>
    );
  }

  return null;
}

