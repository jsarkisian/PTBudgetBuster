import React, { useRef, useEffect, useState } from 'react';

export default function OutputPanel({ outputs, onClear }) {
  const scrollRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState('all');
  const [lightboxSrc, setLightboxSrc] = useState(null);

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
              onImageClick={setLightboxSrc}
            />
          ))
        )}
      </div>

      {/* Lightbox */}
      {lightboxSrc && (
        <Lightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
      )}
    </div>
  );
}

function Lightbox({ src, onClose }) {
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 cursor-pointer"
      onClick={onClose}
    >
      <div className="relative max-w-[90vw] max-h-[90vh]" onClick={e => e.stopPropagation()}>
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 w-8 h-8 bg-dark-700 hover:bg-dark-600 rounded-full flex items-center justify-center text-gray-300 text-lg border border-dark-500 z-10"
        >
          ×
        </button>
        <img
          src={src}
          alt="Screenshot"
          className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg border border-dark-600 shadow-2xl"
        />
        <div className="mt-2 flex justify-center">
          <a
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost text-xs px-3 py-1"
          >
            Open in new tab ↗
          </a>
        </div>
      </div>
    </div>
  );
}

// Patterns that indicate screenshot file paths in tool output
// Matches paths like: /opt/pentest/data/screenshots/https---domain.com.jpeg
// Or: /opt/pentest/output/screenshot/subdomain.domain.com/hash.png
// Or: screenshots/filename.jpeg
// Or any path ending in an image extension
const IMAGE_PATH_REGEX = /(?:\/opt\/pentest\/[^\s"']+\.(?:png|jpg|jpeg|gif|webp|bmp))/gi;
const REL_SCREENSHOT_REGEX = /(?:(?:screenshots?|output\/screenshot)\/[^\s"']+\.(?:png|jpg|jpeg|gif|webp|bmp))/gi;
const GENERIC_IMG_PATH_REGEX = /(?:\/[\w./_-]+\.(?:png|jpg|jpeg|gif|webp|bmp))/gi;

function extractImagePaths(text) {
  if (!text) return [];
  const paths = new Set();

  // Match /opt/pentest/... paths (most specific)
  const optMatches = text.match(IMAGE_PATH_REGEX) || [];
  optMatches.forEach(p => paths.add(p));

  // Match relative screenshot paths
  const relMatches = text.match(REL_SCREENSHOT_REGEX) || [];
  relMatches.forEach(p => paths.add(p));

  // Match any absolute path to an image
  const genericMatches = text.match(GENERIC_IMG_PATH_REGEX) || [];
  genericMatches.forEach(p => {
    // Skip very short paths that are likely false positives
    if (p.length > 8) paths.add(p);
  });

  return [...paths];
}

function buildImageUrl(path) {
  // Strip /opt/pentest/ prefix if present, since the proxy searches relative to /opt/pentest/
  let cleanPath = path;
  if (cleanPath.startsWith('/opt/pentest/')) {
    cleanPath = cleanPath.replace('/opt/pentest/', '');
  }
  // Don't double-encode slashes
  return `/api/images/${cleanPath}`;
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

    // Extract screenshot paths from output and command
    const imagePaths = extractImagePaths(output + '\n' + command + '\n' + error);

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
          <span className={`text-[10px] ${isSuccess ? 'text-accent-green' : 'text-accent-red'}`}>
            {result.status}
          </span>
          {imagePaths.length > 0 && (
            <span className="text-[10px] bg-accent-blue/20 text-accent-blue px-1.5 rounded">
              📸 {imagePaths.length}
            </span>
          )}
          <span className="text-gray-500 text-xs ml-auto">
            {expanded ? '▼' : '▶'}
          </span>
        </div>

        {expanded && (
          <div className="px-3 pb-3 border-t border-dark-600">
            {/* Screenshots */}
            {imagePaths.length > 0 && (
              <div className="mt-2 mb-2">
                <div className="text-xs text-gray-400 font-medium mb-1.5">Screenshots</div>
                <div className="flex flex-wrap gap-2">
                  {imagePaths.map((imgPath, idx) => (
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

function ScreenshotThumb({ path, onClick }) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);

  const imageUrl = buildImageUrl(path);

  if (errored) {
    return (
      <div className="w-36 h-24 bg-dark-700 border border-dark-500 rounded flex items-center justify-center text-xs text-gray-500">
        <div className="text-center px-1">
          <div>📸</div>
          <div className="truncate max-w-[130px]" title={path}>
            {path.split('/').pop()}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="relative cursor-pointer group"
      onClick={() => onClick(imageUrl)}
    >
      <div className={`w-36 h-24 bg-dark-700 border border-dark-500 rounded overflow-hidden ${
        !loaded ? 'animate-pulse' : ''
      }`}>
        <img
          src={imageUrl}
          alt={path.split('/').pop()}
          className={`w-full h-full object-cover transition-opacity ${loaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setLoaded(true)}
          onError={() => setErrored(true)}
        />
      </div>
      {/* Hover overlay */}
      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded flex items-center justify-center">
        <span className="text-white text-xs font-medium">🔍 View</span>
      </div>
      {/* Filename */}
      <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-1 py-0.5 rounded-b">
        <span className="text-[9px] text-gray-300 truncate block" title={path}>
          {path.split('/').pop()}
        </span>
      </div>
    </div>
  );
}
