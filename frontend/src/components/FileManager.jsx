import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';
import { buildImageUrl, Lightbox } from './ImageUtils';

// ── helpers ────────────────────────────────────────────────────────────

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg']);

function isImage(filename) {
  return IMAGE_EXTS.has(filename.split('.').pop()?.toLowerCase());
}

function fmtSize(bytes) {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function relativeTime(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const TOOL_ICONS = {
  httpx: '🌐', subfinder: '🔍', amass: '🔍', dnsx: '🔍', dnsrecon: '🔍',
  nmap: '🔭', naabu: '🔭', masscan: '🔭',
  nuclei: '⚡', nikto: '⚡', sqlmap: '⚡', wpscan: '⚡',
  ffuf: '📂', gobuster: '📂', katana: '🕷', gospider: '🕷',
  gau: '🕷', waybackurls: '🕷', tlsx: '🔒', sslscan: '🔒',
  bash: '⌨', curl: '🌐', wget: '🌐',
};

function toolIcon(tool) {
  return TOOL_ICONS[tool?.toLowerCase()] || '🔧';
}

function fileIcon(filename) {
  if (isImage(filename)) return '🖼';
  const ext = filename.split('.').pop()?.toLowerCase();
  if (['txt', 'log', 'out'].includes(ext)) return '📄';
  if (['json', 'xml', 'yaml', 'yml'].includes(ext)) return '{}';
  if (['csv'].includes(ext)) return '📊';
  if (['html', 'htm'].includes(ext)) return '🌐';
  if (['zip', 'tar', 'gz'].includes(ext)) return '🗜';
  return '📄';
}

// ── FileViewer ──────────────────────────────────────────────────────────

function FileViewer({ file, onClose, onDelete }) {
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lightbox, setLightbox] = useState(null);
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!file) return;
    if (isImage(file.name)) {
      setContent({ type: 'image' });
      return;
    }
    setLoading(true);
    setContent(null);
    api.readFile(file.path)
      .then(d => setContent({ type: 'text', text: d.content || '' }))
      .catch(e => setContent({ type: 'error', text: e.message }))
      .finally(() => setLoading(false));
  }, [file?.path]);

  if (!file) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
        Select a file to view its contents
      </div>
    );
  }

  const imageUrl = buildImageUrl(file.path);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2 border-b border-dark-600 bg-dark-900 flex items-center gap-2 shrink-0">
        <span className="text-base leading-none">{fileIcon(file.name)}</span>
        <span className="font-mono text-xs text-gray-200 flex-1 truncate">{file.name}</span>
        <span className="text-xs text-gray-600 shrink-0">{fmtSize(file.size)}</span>
        {isImage(file.name) && (
          <>
            <button
              onClick={() => setLightbox({ src: imageUrl, filename: file.name })}
              className="btn-ghost text-xs px-2 py-1 shrink-0"
            >
              Expand ↗
            </button>
            <a
              href={imageUrl}
              download={file.name}
              className="btn-ghost text-xs px-2 py-1 shrink-0"
            >
              ↓ Download
            </a>
          </>
        )}
        {!isImage(file.name) && content?.type === 'text' && (
          <button
            onClick={() => {
              navigator.clipboard.writeText(content.text || '');
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="btn-ghost text-xs px-2 py-1 shrink-0"
          >
            {copied ? '✓ Copied' : '⎘ Copy'}
          </button>
        )}
        <button
          onClick={async () => {
            if (!confirmDelete) {
              setConfirmDelete(true);
              setTimeout(() => setConfirmDelete(false), 3000);
              return;
            }
            setDeleting(true);
            try { await onDelete(file); } finally { setDeleting(false); setConfirmDelete(false); }
          }}
          disabled={deleting}
          className={`shrink-0 text-xs px-2 py-1 rounded border transition-colors ${
            confirmDelete
              ? 'bg-red-600 border-red-600 text-white'
              : 'btn-ghost text-gray-500 hover:text-red-400 hover:border-red-500/50'
          }`}
          title={confirmDelete ? 'Click again to permanently delete' : 'Delete file'}
        >
          {deleting ? '…' : confirmDelete ? 'Confirm delete?' : '🗑'}
        </button>
        <button onClick={onClose} className="btn-ghost text-xs px-2 py-1 text-gray-500 shrink-0">✕</button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto bg-dark-950 p-4">
        {loading ? (
          <div className="text-gray-500 text-xs">Loading…</div>
        ) : content?.type === 'image' ? (
          <img
            src={imageUrl}
            alt={file.name}
            className="max-w-full max-h-full object-contain cursor-pointer rounded border border-dark-600"
            onClick={() => setLightbox({ src: imageUrl, filename: file.name })}
          />
        ) : content?.type === 'text' ? (
          <pre className="text-gray-300 text-[11px] font-mono whitespace-pre-wrap break-words leading-relaxed">
            {content.text || <span className="text-gray-600 italic">Empty file</span>}
          </pre>
        ) : content?.type === 'error' ? (
          <div className="text-red-400 text-xs font-mono">{content.text}</div>
        ) : null}
      </div>

      {lightbox && (
        <Lightbox src={lightbox.src} filename={lightbox.filename} onClose={() => setLightbox(null)} />
      )}
    </div>
  );
}

// ── FileRow ─────────────────────────────────────────────────────────────

function FileRow({ file, selected, onSelect, onDelete }) {
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDeleteClick = async (e) => {
    e.stopPropagation();
    if (!confirm) {
      setConfirm(true);
      setTimeout(() => setConfirm(false), 3000);
      return;
    }
    setDeleting(true);
    try {
      await onDelete(file);
    } finally {
      setDeleting(false);
      setConfirm(false);
    }
  };

  return (
    <div
      onClick={() => onSelect(file)}
      className={`group w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-dark-700 transition-colors cursor-pointer ${
        selected ? 'bg-dark-700 text-gray-100' : 'text-gray-300'
      }`}
    >
      <span className="text-sm shrink-0 leading-none">{fileIcon(file.name)}</span>
      <span className="flex-1 truncate font-mono">{file.name}</span>
      <span className="text-gray-600 shrink-0 tabular-nums">{fmtSize(file.size)}</span>
      <button
        onClick={handleDeleteClick}
        disabled={deleting}
        className={`shrink-0 w-5 h-5 rounded flex items-center justify-center text-[10px] transition-all ${
          confirm
            ? 'bg-red-600 text-white opacity-100'
            : 'opacity-0 group-hover:opacity-100 bg-dark-600 text-gray-500 hover:bg-red-600 hover:text-white'
        }`}
        title={confirm ? 'Click again to confirm delete' : 'Delete file'}
      >
        {deleting ? '…' : confirm ? '!' : '×'}
      </button>
    </div>
  );
}

// ── RunSection ──────────────────────────────────────────────────────────

function RunSection({ run, selectedFile, onSelectFile, onDeleteFile }) {
  const [expanded, setExpanded] = useState(false);
  const [files, setFiles] = useState(run.files);

  const handleDelete = async (file) => {
    await onDeleteFile(file);
    setFiles(prev => prev.filter(f => f.path !== file.path));
  };

  if (files.length === 0) return null;

  return (
    <div className="border-b border-dark-800 last:border-0">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-dark-700/50 transition-colors"
      >
        <span className="text-sm shrink-0 leading-none">{toolIcon(run.tool)}</span>
        <span className="text-xs font-semibold text-gray-200 shrink-0">{run.label}</span>
        <span className="text-[10px] text-gray-600 flex-1 truncate ml-1">
          {files.length} file{files.length !== 1 ? 's' : ''} · {fmtSize(run.total_size)}
        </span>
        <span className="text-[10px] text-gray-600 shrink-0 tabular-nums">{relativeTime(run.timestamp)}</span>
        <span className="text-gray-600 text-[10px] shrink-0 ml-1">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="bg-dark-950/50">
          {files.map((f, i) => (
            <FileRow
              key={f.path || i}
              file={f}
              selected={selectedFile?.path === f.path}
              onSelect={onSelectFile}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── SessionSection ──────────────────────────────────────────────────────

function SessionSection({ session, selectedFile, onSelectFile, onDeleteFile }) {
  const [expanded, setExpanded] = useState(true);
  const totalFiles = session.runs.reduce((s, r) => s + r.file_count, 0);

  return (
    <div className="border-b border-dark-600">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-dark-800 hover:bg-dark-700 transition-colors"
      >
        <span className="text-sm shrink-0">🗂</span>
        <span className="text-xs font-semibold text-gray-100 flex-1 truncate">{session.name}</span>
        <span className="text-[10px] text-gray-500 shrink-0">
          {session.runs.length} run{session.runs.length !== 1 ? 's' : ''} · {totalFiles} file{totalFiles !== 1 ? 's' : ''}
        </span>
        <span className="text-gray-600 text-[10px] shrink-0 ml-1">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <div className="pl-2">
          {session.runs.map(run => (
            <RunSection
              key={run.task_id}
              run={run}
              selectedFile={selectedFile}
              onSelectFile={onSelectFile}
              onDeleteFile={onDeleteFile}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────

export default function FileManager() {
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState(null);
  const [search, setSearch] = useState('');
  const [deleteError, setDeleteError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    api.getWorkspace()
      .then(setWorkspace)
      .catch(() => setWorkspace({ sessions: [], loose_files: [], unknown_dirs: [] }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDeleteFile = useCallback(async (file) => {
    setDeleteError(null);
    await api.deleteFile(file.path);
    // Clear viewer if this file is open
    setSelectedFile(prev => (prev?.path === file.path ? null : prev));
    // Remove from loose_files and unknown_dirs in workspace state
    setWorkspace(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        loose_files: prev.loose_files.filter(f => f.path !== file.path),
        unknown_dirs: prev.unknown_dirs.map(d => ({
          ...d,
          files: d.files.filter(f => f.path !== file.path),
        })).filter(d => d.files.length > 0),
      };
    });
  }, []);

  const hasContent = workspace && (
    workspace.sessions.length > 0 ||
    workspace.loose_files.length > 0 ||
    workspace.unknown_dirs.length > 0
  );

  // Flat search across all files
  const searchLower = search.trim().toLowerCase();
  const filteredSessions = searchLower
    ? workspace?.sessions.map(sess => ({
        ...sess,
        runs: sess.runs.map(run => ({
          ...run,
          files: run.files.filter(f => f.name.toLowerCase().includes(searchLower)),
        })).filter(run => run.files.length > 0),
      })).filter(sess => sess.runs.length > 0)
    : workspace?.sessions;

  const filteredLoose = searchLower
    ? workspace?.loose_files.filter(f => f.name.toLowerCase().includes(searchLower))
    : workspace?.loose_files;

  const filteredUnknown = searchLower
    ? workspace?.unknown_dirs.map(d => ({
        ...d,
        files: d.files.filter(f => f.name.toLowerCase().includes(searchLower)),
      })).filter(d => d.files.length > 0)
    : workspace?.unknown_dirs;

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left pane */}
      <div className="w-80 flex flex-col border-r border-dark-600 bg-dark-900 shrink-0">
        {/* Toolbar */}
        <div className="px-3 py-2 border-b border-dark-600 flex items-center gap-2 shrink-0">
          <span className="text-xs font-semibold text-gray-300">Workspace Files</span>
          {deleteError && (
            <span className="text-[10px] text-red-400 flex-1 truncate">{deleteError}</span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="ml-auto btn-ghost text-xs px-2 py-1 disabled:opacity-50"
            title="Refresh"
          >
            {loading ? '…' : '↺'}
          </button>
        </div>

        {/* Search */}
        <div className="px-3 py-2 border-b border-dark-600 shrink-0">
          <input
            type="text"
            placeholder="Search files…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-dark-800 border border-dark-600 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 outline-none focus:border-accent-blue"
          />
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-6 text-xs text-gray-500 text-center">Loading workspace…</div>
          ) : !hasContent ? (
            <div className="p-6 text-center space-y-2">
              <div className="text-2xl">📭</div>
              <div className="text-xs text-gray-500">No files yet.</div>
              <div className="text-[11px] text-gray-600">
                Files saved by tools and the AI agent will appear here, organized by engagement.
              </div>
            </div>
          ) : (
            <>
              {/* By engagement */}
              {filteredSessions?.map(sess => (
                <SessionSection
                  key={sess.id}
                  session={sess}
                  selectedFile={selectedFile}
                  onSelectFile={setSelectedFile}
                  onDeleteFile={handleDeleteFile}
                />
              ))}

              {/* Loose files (not tied to any session) */}
              {filteredLoose?.length > 0 && (
                <div className="border-b border-dark-600">
                  <div className="px-3 py-2 bg-dark-800 text-xs font-semibold text-gray-400">
                    Workspace root
                  </div>
                  {filteredLoose.map((f, i) => (
                    <FileRow
                      key={f.path || i}
                      file={f}
                      selected={selectedFile?.path === f.path}
                      onSelect={setSelectedFile}
                      onDelete={handleDeleteFile}
                    />
                  ))}
                </div>
              )}

              {/* Unknown dirs (files with no session mapping) */}
              {filteredUnknown?.length > 0 && (
                <div className="border-b border-dark-600">
                  <div className="px-3 py-2 bg-dark-800 text-xs font-semibold text-gray-400">
                    Other
                  </div>
                  {filteredUnknown.map(dir => (
                    <div key={dir.name}>
                      <div className="px-3 py-1 text-[10px] text-gray-600 font-mono">{dir.name}/</div>
                      {dir.files.map((f, i) => (
                        <FileRow
                          key={f.path || i}
                          file={f}
                          selected={selectedFile?.path === f.path}
                          onSelect={setSelectedFile}
                          onDelete={handleDeleteFile}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Right pane */}
      <div className="flex-1 flex flex-col bg-dark-950 overflow-hidden">
        <FileViewer
          file={selectedFile}
          onClose={() => setSelectedFile(null)}
          onDelete={handleDeleteFile}
        />
      </div>
    </div>
  );
}
