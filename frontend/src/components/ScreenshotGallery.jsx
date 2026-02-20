import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { Lightbox, ScreenshotThumb } from './ImageUtils';

export default function ScreenshotGallery() {
  const [screenshots, setScreenshots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('');
  const [lightbox, setLightbox] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listScreenshots();
      setScreenshots(data.screenshots || []);
    } catch (e) {
      console.error('Failed to load screenshots:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const filtered = filter
    ? screenshots.filter(s => s.name?.toLowerCase().includes(filter.toLowerCase()) || s.path?.toLowerCase().includes(filter.toLowerCase()))
    : screenshots;

  return (
    <div className="h-full flex flex-col">
      <div className="panel-header shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-300">Screenshots</span>
          <span className="text-xs text-gray-500">{filtered.length} of {screenshots.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter..."
            className="text-xs bg-dark-700 border border-dark-500 rounded px-2 py-1 text-gray-300 w-40"
          />
          <button
            onClick={load}
            disabled={loading}
            className="btn-ghost text-xs px-2 py-1"
          >
            {loading ? '...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 bg-dark-950">
        {loading && screenshots.length === 0 ? (
          <div className="text-center text-gray-600 text-xs py-12">Loading screenshots...</div>
        ) : filtered.length === 0 ? (
          <div className="text-center text-gray-600 text-xs py-12">
            {screenshots.length === 0 ? 'No screenshots yet. Run a tool that captures screenshots.' : 'No screenshots match filter.'}
          </div>
        ) : (
          <div className="flex flex-wrap gap-3">
            {filtered.map((ss, idx) => (
              <ScreenshotThumb
                key={idx}
                path={ss.path}
                onClick={(src, filename) => setLightbox({ src, filename })}
              />
            ))}
          </div>
        )}
      </div>

      {lightbox && (
        <Lightbox src={lightbox.src} filename={lightbox.filename} onClose={() => setLightbox(null)} />
      )}
    </div>
  );
}
