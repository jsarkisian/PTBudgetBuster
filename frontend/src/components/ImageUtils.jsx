import React, { useState, useEffect } from 'react';

// Patterns that indicate screenshot file paths in tool output
const IMAGE_PATH_REGEX = /(?:\/opt\/pentest\/[^\s"']+\.(?:png|jpg|jpeg|gif|webp|bmp))/gi;
const REL_SCREENSHOT_REGEX = /(?:(?:screenshots?|output\/screenshot)\/[^\s"']+\.(?:png|jpg|jpeg|gif|webp|bmp))/gi;
const GENERIC_IMG_PATH_REGEX = /(?:\/[\w./_-]+\.(?:png|jpg|jpeg|gif|webp|bmp))/gi;

export function extractImagePaths(text) {
  if (!text) return [];
  const paths = new Set();

  const optMatches = text.match(IMAGE_PATH_REGEX) || [];
  optMatches.forEach(p => paths.add(p));

  const relMatches = text.match(REL_SCREENSHOT_REGEX) || [];
  relMatches.forEach(p => paths.add(p));

  const genericMatches = text.match(GENERIC_IMG_PATH_REGEX) || [];
  genericMatches.forEach(p => {
    if (p.length > 8) paths.add(p);
  });

  return [...paths];
}

export function buildImageUrl(path) {
  let cleanPath = path;
  if (cleanPath.startsWith('/opt/pentest/')) {
    cleanPath = cleanPath.replace('/opt/pentest/', '');
  }
  return `/api/images/${cleanPath}`;
}

export function Lightbox({ src, filename, onClose }) {
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
          alt={filename || 'Screenshot'}
          className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg border border-dark-600 shadow-2xl"
        />
        <div className="mt-2 flex justify-center gap-3">
          {filename && (
            <span className="text-xs text-gray-400">{filename}</span>
          )}
          <a
            href={src}
            download
            className="btn-ghost text-xs px-3 py-1"
            onClick={e => e.stopPropagation()}
          >
            Download ↓
          </a>
          <a
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost text-xs px-3 py-1"
            onClick={e => e.stopPropagation()}
          >
            Open in new tab ↗
          </a>
        </div>
      </div>
    </div>
  );
}

export function ScreenshotThumb({ path, onClick }) {
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
      onClick={() => onClick(imageUrl, path.split('/').pop())}
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
      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded flex items-center justify-center">
        <span className="text-white text-xs font-medium">🔍 View</span>
      </div>
      <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-1 py-0.5 rounded-b">
        <span className="text-[9px] text-gray-300 truncate block" title={path}>
          {path.split('/').pop()}
        </span>
      </div>
    </div>
  );
}
