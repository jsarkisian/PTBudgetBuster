import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { buildImageUrl } from './ImageUtils';

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg']);

function isImage(filename) {
  const ext = filename.split('.').pop()?.toLowerCase();
  return IMAGE_EXTENSIONS.has(ext);
}

export default function FileManager() {
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fileContent, setFileContent] = useState(null); // {path, content, type}
  const [fileLoading, setFileLoading] = useState(false);

  const loadDir = async (path) => {
    setLoading(true);
    setFileContent(null);
    try {
      const data = await api.listFiles(path);
      setEntries(data.entries || data.files || []);
      setCurrentPath(path);
    } catch (e) {
      console.error('Failed to list directory:', e);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadDir(''); }, []);

  const handleEntryClick = async (entry) => {
    if (entry.type === 'directory' || entry.is_dir) {
      const newPath = currentPath ? `${currentPath}/${entry.name}` : entry.name;
      loadDir(newPath);
    } else {
      const filePath = currentPath ? `${currentPath}/${entry.name}` : entry.name;
      if (isImage(entry.name)) {
        setFileContent({ path: filePath, content: null, type: 'image' });
        return;
      }
      setFileLoading(true);
      setFileContent(null);
      try {
        const data = await api.readFile(filePath);
        setFileContent({ path: filePath, content: data.content || '', type: 'text' });
      } catch (e) {
        setFileContent({ path: filePath, content: `Error loading file: ${e.message}`, type: 'text' });
      } finally {
        setFileLoading(false);
      }
    }
  };

  const navigateTo = (path) => {
    loadDir(path);
  };

  // Build breadcrumb segments from currentPath
  const breadcrumbSegments = currentPath
    ? currentPath.split('/').filter(Boolean)
    : [];

  return (
    <div className="h-full flex">
      {/* Left pane: directory browser */}
      <div className="w-72 flex flex-col border-r border-dark-600 bg-dark-900 shrink-0">
        {/* Breadcrumb */}
        <div className="px-3 py-2 border-b border-dark-600 flex items-center flex-wrap gap-1 text-xs min-h-[36px]">
          <button
            onClick={() => navigateTo('')}
            className="text-accent-blue hover:text-accent-cyan"
          >
            /
          </button>
          {breadcrumbSegments.map((seg, idx) => {
            const segPath = breadcrumbSegments.slice(0, idx + 1).join('/');
            return (
              <React.Fragment key={segPath}>
                <span className="text-gray-600">/</span>
                <button
                  onClick={() => navigateTo(segPath)}
                  className="text-accent-blue hover:text-accent-cyan"
                >
                  {seg}
                </button>
              </React.Fragment>
            );
          })}
        </div>

        {/* Directory listing */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-xs text-gray-500 text-center">Loading...</div>
          ) : entries.length === 0 ? (
            <div className="p-4 text-xs text-gray-500 text-center">Empty directory</div>
          ) : (
            entries.map((entry, idx) => {
              const isDir = entry.type === 'directory' || entry.is_dir;
              return (
                <div
                  key={idx}
                  onClick={() => handleEntryClick(entry)}
                  className="px-3 py-1.5 cursor-pointer hover:bg-dark-700 flex items-center gap-2 text-xs border-b border-dark-800"
                >
                  <span className={isDir ? 'text-accent-yellow' : 'text-gray-400'}>
                    {isDir ? '📁' : '📄'}
                  </span>
                  <span className={`truncate ${isDir ? 'text-gray-200 font-medium' : 'text-gray-300'}`}>
                    {entry.name}
                  </span>
                  {entry.size != null && !isDir && (
                    <span className="ml-auto text-gray-600 shrink-0">
                      {entry.size < 1024 ? `${entry.size}B` : entry.size < 1048576 ? `${(entry.size/1024).toFixed(1)}K` : `${(entry.size/1048576).toFixed(1)}M`}
                    </span>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Right pane: file content */}
      <div className="flex-1 flex flex-col bg-dark-950 overflow-hidden">
        {fileLoading ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 text-xs">
            Loading file...
          </div>
        ) : fileContent ? (
          <>
            <div className="px-4 py-2 border-b border-dark-600 bg-dark-900 text-xs text-gray-400 font-mono shrink-0">
              {fileContent.path}
            </div>
            <div className="flex-1 overflow-auto p-4">
              {fileContent.type === 'image' ? (
                <img
                  src={buildImageUrl(fileContent.path)}
                  alt={fileContent.path}
                  className="max-w-full max-h-full object-contain"
                />
              ) : (
                <pre className="terminal text-gray-300 text-xs whitespace-pre-wrap break-words">
                  {fileContent.content}
                </pre>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">
            Select a file to view its contents
          </div>
        )}
      </div>
    </div>
  );
}
