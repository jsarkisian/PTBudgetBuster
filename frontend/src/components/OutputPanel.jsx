import React, { useRef, useEffect, useState, useMemo } from 'react';
import { Lightbox, ScreenshotThumb, extractImagePaths } from './ImageUtils';

// ── Helpers ────────────────────────────────────────────────────────────

/**
 * Merge separate start/result entries (matched by task_id) into single
 * "execution" entries. Non-tool entries pass through unchanged.
 */
function pairOutputs(outputs) {
  const result = [];
  const idToIdx = new Map();

  for (const entry of outputs) {
    if (entry.type === 'start') {
      const idx = result.length;
      idToIdx.set(entry.id, idx);
      result.push({ type: 'execution', id: entry.id, tool: entry.tool, start: entry, result: null });
    } else if (entry.type === 'result') {
      const idx = idToIdx.get(entry.id);
      if (idx !== undefined) {
        result[idx] = { ...result[idx], result: entry };
      } else {
        // Orphaned result (history reload without matching start)
        result.push({ type: 'execution', id: entry.id, tool: entry.tool, start: null, result: entry });
      }
    } else {
      result.push(entry);
    }
  }
  return result;
}

/**
 * Build a human-readable CLI command string from tool + parameters.
 */
function formatCommand(tool, parameters = {}) {
  if (!parameters) return tool;

  // Free-form CLI args
  const rawArgs = parameters.__raw_args__;
  if (rawArgs && rawArgs.trim()) return `${tool} ${rawArgs.trim()}`;

  // Bash: the command IS the payload
  if (tool === 'bash' && parameters.command) return parameters.command;

  const parts = [tool];
  for (const [k, v] of Object.entries(parameters)) {
    if (['__raw_args__', '__scope__', 'command'].includes(k)) continue;
    if (typeof v === 'boolean') {
      if (v) parts.push(`--${k}`);
    } else if (Array.isArray(v)) {
      parts.push(`--${k} ${v.join(',')}`);
    } else if (v !== null && v !== '' && v !== undefined) {
      parts.push(`--${k} ${v}`);
    }
  }

  // If no args were added but we have a scope, show it as the target
  if (parts.length === 1 && parameters.__scope__) {
    const scope = Array.isArray(parameters.__scope__) ? parameters.__scope__ : [parameters.__scope__];
    parts.push(scope.slice(0, 3).join(', '));
    if (scope.length > 3) parts.push(`+${scope.length - 3} more`);
  }

  return parts.join(' ');
}

/**
 * Extract a one-line human summary from tool output.
 */
function summarizeOutput(tool, output, status) {
  if (status === 'killed') return 'stopped';
  if (status === 'timeout') return 'timed out';
  if (status === 'error' || status === 'failed') return status;

  if (!output || !output.trim()) return 'no output';
  const lines = output.split('\n').filter(l => l.trim());

  // Subdomain / DNS discovery
  if (['subfinder', 'amass', 'dnsx', 'dnsrecon', 'fierce', 'theharvester'].includes(tool)) {
    const hosts = lines.filter(l => /^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}$/i.test(l.trim()));
    if (hosts.length > 0) return `${hosts.length} host${hosts.length !== 1 ? 's' : ''} found`;
  }

  // Port scanners
  if (['naabu', 'masscan'].includes(tool)) {
    const ports = lines.filter(l => l.includes(':') && l.match(/\d+:\d+/));
    if (ports.length > 0) return `${ports.length} open port${ports.length !== 1 ? 's' : ''}`;
  }
  if (tool === 'nmap') {
    const open = (output.match(/\d+\/(tcp|udp)\s+open/g) || []);
    if (open.length > 0) return `${open.length} open port${open.length !== 1 ? 's' : ''}`;
  }

  // HTTP probing
  if (tool === 'httpx') {
    const live = lines.filter(l => l.match(/^https?:\/\//i));
    if (live.length > 0) return `${live.length} live host${live.length !== 1 ? 's' : ''}`;
  }

  // Vulnerability scanners
  if (tool === 'nuclei') {
    const severities = ['critical', 'high', 'medium', 'low', 'info'];
    const matches = lines.filter(l => severities.some(s => l.toLowerCase().includes(`[${s}]`)));
    if (matches.length > 0) return `${matches.length} finding${matches.length !== 1 ? 's' : ''}`;
    return 'no findings';
  }
  if (tool === 'nikto') {
    const items = lines.filter(l => l.startsWith('+'));
    if (items.length > 0) return `${items.length} item${items.length !== 1 ? 's' : ''}`;
  }

  // Web crawlers
  if (['katana', 'gospider', 'gau', 'waybackurls'].includes(tool)) {
    const urls = lines.filter(l => l.match(/^https?:\/\//i));
    if (urls.length > 0) return `${urls.length} URL${urls.length !== 1 ? 's' : ''} found`;
  }

  // Fuzzers
  if (['ffuf', 'gobuster', 'wfuzz', 'dirb'].includes(tool)) {
    const hits = lines.filter(l => l.match(/\b2\d\d\b/) || l.toLowerCase().includes('found'));
    if (hits.length > 0) return `${hits.length} path${hits.length !== 1 ? 's' : ''} found`;
  }

  // Generic fallback: line count
  return `${lines.length} line${lines.length !== 1 ? 's' : ''}`;
}

/**
 * Split output into colorized lines for easier reading.
 */
function colorizeOutput(output) {
  if (!output) return [];
  return output.split('\n').map((line, i) => {
    const lower = line.toLowerCase();
    let cls = 'text-gray-400';

    // Nuclei severity
    if (line.includes('[critical]')) cls = 'text-red-400 font-semibold';
    else if (line.includes('[high]')) cls = 'text-orange-400 font-semibold';
    else if (line.includes('[medium]')) cls = 'text-yellow-300';
    else if (line.includes('[low]')) cls = 'text-blue-400';
    else if (line.includes('[info]')) cls = 'text-gray-500';
    // Open ports
    else if (/\d+\/(tcp|udp)\s+open/.test(lower)) cls = 'text-green-400';
    // host:port open (naabu/masscan)
    else if (/\d+\.\d+\.\d+\.\d+:\d+/.test(line)) cls = 'text-green-300';
    // Errors
    else if (/\berror\b|\bfailed\b|\bdenied\b|\[err\]/.test(lower)) cls = 'text-red-400';
    // Warnings
    else if (/\bwarn(ing)?\b/.test(lower)) cls = 'text-yellow-400';
    // Live HTTP URLs (httpx output lines)
    else if (/^https?:\/\//.test(line)) cls = 'text-cyan-300';
    // Plain IP addresses
    else if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/.test(line.trim())) cls = 'text-green-300';
    // Bare hostnames / subdomains
    else if (/^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}$/i.test(line.trim())) cls = 'text-cyan-400';
    // Nikto findings
    else if (line.startsWith('+')) cls = 'text-yellow-300';

    return { line, cls, key: i };
  });
}

// ── Tool metadata ──────────────────────────────────────────────────────

const TOOL_ICONS = {
  subfinder: '🔍', dnsx: '🔍', amass: '🔍', dnsrecon: '🔍', fierce: '🔍', theharvester: '🔍',
  httpx: '🌐', whatweb: '🌐', wafw00f: '🛡', gowitness: '📸',
  nmap: '🔭', naabu: '🔭', masscan: '🔭',
  nuclei: '⚡', nikto: '⚡', sqlmap: '⚡', wpscan: '⚡',
  ffuf: '📂', gobuster: '📂', wfuzz: '📂', dirb: '📂',
  katana: '🕷', gospider: '🕷', gau: '🕷', waybackurls: '🕷',
  tlsx: '🔒', sslscan: '🔒', testssl: '🔒',
  uncover: '🌍', shodan: '🌍',
  crackmapexec: '🪓', hydra: '🪓', responder: '🎣',
  bash: '⌨',
};

const TOOL_DESCRIPTIONS = {
  subfinder: 'Subdomain enumeration',
  dnsx: 'DNS resolution',
  amass: 'Subdomain enumeration',
  httpx: 'HTTP probing',
  nmap: 'Port & service scan',
  naabu: 'Port scan',
  masscan: 'Port scan',
  nuclei: 'Vulnerability scan',
  nikto: 'Web server scan',
  ffuf: 'Web fuzzing',
  gobuster: 'Directory brute-force',
  katana: 'Web crawler',
  waybackurls: 'URL history',
  whatweb: 'Tech fingerprint',
  wafw00f: 'WAF detection',
  tlsx: 'TLS analysis',
  sslscan: 'SSL scan',
  bash: 'Custom command',
};

// ── Main component ─────────────────────────────────────────────────────

export default function OutputPanel({ outputs, onClear }) {
  const scrollRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState('all');
  const [lightbox, setLightbox] = useState(null);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [outputs, autoScroll]);

  const paired = useMemo(() => pairOutputs(outputs), [outputs]);

  const execCount = paired.filter(p => p.type === 'execution').length;

  const filtered = filter === 'all'
    ? paired
    : paired.filter(o => {
        if (o.type === 'auto_status') return true;
        const src = o.start?.source || o.result?.source || '';
        return src === filter;
      });

  return (
    <div className="h-full flex flex-col">
      <div className="panel-header shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-300">Output</span>
          <span className="text-xs text-gray-500">
            {execCount} run{execCount !== 1 ? 's' : ''}
          </span>
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
          <button onClick={onClear} className="btn-ghost text-xs px-2 py-1">Clear</button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-1.5 bg-dark-950">
        {filtered.length === 0 ? (
          <div className="text-center text-gray-600 text-xs py-8">
            Tool output will appear here...
          </div>
        ) : (
          filtered.map((entry, i) => {
            if (entry.type === 'auto_status') {
              return <StatusLine key={`s-${i}`} entry={entry} />;
            }
            if (entry.type === 'execution') {
              return (
                <ExecutionCard
                  key={entry.id || i}
                  entry={entry}
                  onImageClick={(src, filename) => setLightbox({ src, filename })}
                />
              );
            }
            return null;
          })
        )}
      </div>

      {lightbox && (
        <Lightbox src={lightbox.src} filename={lightbox.filename} onClose={() => setLightbox(null)} />
      )}
    </div>
  );
}

// ── Auto-status: thin subtle separator line ────────────────────────────

function StatusLine({ entry }) {
  return (
    <div className="flex items-center gap-2 py-0.5 px-1 text-[11px] text-gray-600">
      <span className="w-1.5 h-1.5 rounded-full bg-accent-purple/40 shrink-0" />
      <span className="flex-1 truncate">{entry.message}</span>
      <span className="shrink-0 tabular-nums">
        {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : ''}
      </span>
    </div>
  );
}

// ── Execution card: unified start+result view ──────────────────────────

function ExecutionCard({ entry, onImageClick }) {
  const { start, result, tool } = entry;
  const pending = !result;
  const taskResult = result?.result || {};
  const isSuccess = taskResult.status === 'completed';
  const status = taskResult.status;
  const output = taskResult.output || '';
  const error = taskResult.error || '';
  const source = start?.source || result?.source || 'manual';
  const timestamp = start?.timestamp || result?.timestamp;
  const params = start?.parameters || {};

  // Start expanded while running; collapse when result arrives
  const [expanded, setExpanded] = useState(pending);
  const prevPending = useRef(pending);
  useEffect(() => {
    if (prevPending.current && !pending) setExpanded(false);
    prevPending.current = pending;
  }, [pending]);

  const cmd = useMemo(() => formatCommand(tool, params), [tool, params]);
  // Args portion only (strip leading tool name to avoid duplication in header)
  const cmdArgs = cmd.startsWith(tool + ' ') ? cmd.slice(tool.length + 1) : (cmd !== tool ? cmd : '');

  const summary = result ? summarizeOutput(tool, output, status) : null;
  const icon = TOOL_ICONS[tool] || '🔧';
  const desc = TOOL_DESCRIPTIONS[tool];

  // Screenshot detection
  const paramValues = Object.values(params).map(v => String(v)).join('\n');
  const imagePaths = useMemo(() => extractImagePaths([output, error, paramValues].join('\n')), [output, error, paramValues]);
  const [apiScreenshots, setApiScreenshots] = useState([]);
  const isScreenshotTool = tool === 'gowitness' || cmd.includes('screenshot');
  useEffect(() => {
    if (isScreenshotTool && isSuccess && imagePaths.length === 0) {
      fetch('/api/screenshots')
        .then(r => r.json())
        .then(d => { if (d.screenshots?.length) setApiScreenshots(d.screenshots.map(s => s.path)); })
        .catch(() => {});
    }
  }, [isSuccess]);
  const allImages = useMemo(() => [...new Set([...imagePaths, ...apiScreenshots])], [imagePaths, apiScreenshots]);

  const colorizedLines = useMemo(() => colorizeOutput(output), [output]);

  // Card border + header bg by state
  const borderCls = pending
    ? 'border-dark-600'
    : isSuccess ? 'border-accent-green/20' : 'border-accent-red/25';

  return (
    <div className={`border rounded overflow-hidden ${borderCls}`}>
      {/* ── Header (always visible) ── */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-dark-800 hover:bg-dark-700 transition-colors"
      >
        {/* Status dot / icon */}
        <span className="shrink-0 w-4 flex items-center justify-center">
          {pending
            ? <span className="w-2 h-2 rounded-full bg-accent-yellow animate-pulse block" />
            : isSuccess
              ? <span className="text-accent-green text-xs font-bold">✓</span>
              : <span className="text-accent-red text-xs font-bold">✗</span>}
        </span>

        {/* Tool icon + name */}
        <span className="text-sm shrink-0 leading-none">{icon}</span>
        <span className="font-mono text-xs font-semibold text-accent-cyan shrink-0">{tool}</span>

        {/* Description (faint) */}
        {desc && (
          <span className="text-[10px] text-gray-600 shrink-0 hidden sm:inline">{desc}</span>
        )}

        {/* Source badge */}
        {source === 'ai_agent' && (
          <span className="text-[10px] bg-accent-purple/20 text-accent-purple px-1.5 py-0.5 rounded shrink-0">AI</span>
        )}
        {source === 'scheduler' && (
          <span className="text-[10px] bg-accent-yellow/20 text-accent-yellow px-1.5 py-0.5 rounded shrink-0">SCHED</span>
        )}

        {/* Command args preview */}
        {cmdArgs && (
          <span
            className="text-[11px] text-gray-500 font-mono flex-1 truncate min-w-0"
            title={cmd}
          >
            {cmdArgs}
          </span>
        )}
        {!cmdArgs && <span className="flex-1" />}

        {/* Right cluster: summary pill + image count + time + chevron */}
        <div className="flex items-center gap-1.5 shrink-0">
          {summary && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
              pending ? 'text-gray-500'
              : isSuccess ? 'bg-accent-green/10 text-accent-green'
              : 'bg-accent-red/10 text-accent-red'
            }`}>
              {summary}
            </span>
          )}
          {allImages.length > 0 && (
            <span className="text-[10px] bg-accent-blue/15 text-accent-blue px-1.5 py-0.5 rounded">
              📸 {allImages.length}
            </span>
          )}
          <span className="text-gray-600 text-[10px] tabular-nums">
            {timestamp ? new Date(timestamp).toLocaleTimeString() : ''}
          </span>
          <span className="text-gray-600 text-[10px]">{expanded ? '▲' : '▼'}</span>
        </div>
      </button>

      {/* ── Expanded body ── */}
      {expanded && (
        <div className="border-t border-dark-700 divide-y divide-dark-700/60">
          {/* Full command */}
          <div className="px-3 py-2">
            <div className="text-[10px] text-gray-600 mb-1 font-semibold uppercase tracking-wider">Command</div>
            <div className="font-mono text-[11px] text-gray-300 bg-dark-950 px-2.5 py-2 rounded break-all leading-relaxed">
              {cmd}
            </div>
          </div>

          {/* Running indicator (no result yet) */}
          {pending && (
            <div className="px-3 py-3 flex items-center gap-2.5 text-xs text-gray-500">
              <span className="flex gap-0.5">
                {[0, 150, 300].map(d => (
                  <span
                    key={d}
                    className="w-1.5 h-1.5 bg-accent-blue rounded-full animate-bounce"
                    style={{ animationDelay: `${d}ms` }}
                  />
                ))}
              </span>
              Running…
            </div>
          )}

          {/* Screenshots */}
          {allImages.length > 0 && (
            <div className="px-3 py-2">
              <div className="text-[10px] text-gray-600 mb-1.5 font-semibold uppercase tracking-wider">Screenshots</div>
              <div className="flex flex-wrap gap-2">
                {allImages.map((p, idx) => (
                  <ScreenshotThumb key={idx} path={p} onClick={onImageClick} />
                ))}
              </div>
            </div>
          )}

          {/* Output */}
          {output && (
            <div className="px-3 py-2">
              <div className="text-[10px] text-gray-600 mb-1 font-semibold uppercase tracking-wider">
                Output
              </div>
              <div className="bg-dark-950 rounded text-[11px] font-mono max-h-72 overflow-auto">
                {colorizedLines.map(({ line, cls, key }) =>
                  line.trim() ? (
                    <div key={key} className={`px-2.5 py-px leading-relaxed ${cls}`}>{line}</div>
                  ) : (
                    <div key={key} className="h-2" />
                  )
                )}
              </div>
            </div>
          )}

          {/* Errors */}
          {error && (
            <div className="px-3 py-2">
              <div className="text-[10px] text-gray-600 mb-1 font-semibold uppercase tracking-wider">Errors</div>
              <pre className="bg-dark-950 text-red-400 text-[11px] font-mono px-2.5 py-2 rounded max-h-28 overflow-auto leading-relaxed">
                {error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
