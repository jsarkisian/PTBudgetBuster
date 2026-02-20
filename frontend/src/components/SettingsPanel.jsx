import React, { useState, useEffect, useRef } from 'react';
import { api } from '../utils/api';

export default function SettingsPanel({ logoUrl, onLogoChange }) {
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const flash = (msg) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(''), 3000);
  };

  return (
    <div className="h-full flex flex-col">
      <div className="panel-header">
        <span className="text-sm font-semibold text-gray-300">Settings</span>
      </div>

      {error && (
        <div className="mx-3 mt-2 bg-red-500/10 border border-red-500/30 rounded px-3 py-2 text-xs text-red-400">
          {error}
          <button onClick={() => setError('')} className="ml-2 text-red-300">✕</button>
        </div>
      )}
      {success && (
        <div className="mx-3 mt-2 bg-green-500/10 border border-green-500/30 rounded px-3 py-2 text-xs text-green-400">
          {success}
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4">
        <BrandingSection logoUrl={logoUrl} onLogoChange={onLogoChange} onFlash={flash} onError={setError} />
      </div>
    </div>
  );
}

function BrandingSection({ logoUrl, onLogoChange, onFlash, onError }) {
  const fileInputRef = useRef(null);
  const [preview, setPreview] = useState(logoUrl);

  useEffect(() => { setPreview(logoUrl); }, [logoUrl]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      onError('Please select an image file');
      return;
    }
    if (file.size > 1024 * 1024) {
      onError('Image must be under 1MB');
      return;
    }
    const reader = new FileReader();
    reader.onload = async (ev) => {
      const dataUrl = ev.target.result;
      setPreview(dataUrl);
      try {
        await api.setLogo(dataUrl);
        onLogoChange(dataUrl);
        onFlash('Logo updated');
      } catch (err) {
        onError(err.message);
        setPreview(logoUrl);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleReset = async () => {
    try {
      await api.deleteLogo();
      setPreview(null);
      onLogoChange(null);
      onFlash('Logo reset to default');
    } catch (err) {
      onError(err.message);
    }
  };

  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Branding</h3>
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 flex items-center justify-center bg-dark-800 border border-dark-600 rounded-lg shrink-0">
          {preview
            ? <img src={preview} alt="Logo" className="w-10 h-10 object-contain rounded" />
            : <span className="text-2xl">🛡️</span>
          }
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="btn-primary text-xs px-3 py-1.5"
          >
            Upload Logo
          </button>
          {preview && (
            <button
              onClick={handleReset}
              className="btn-ghost text-xs px-3 py-1.5"
            >
              Reset
            </button>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileChange}
        />
        <p className="text-xs text-gray-600">PNG, JPG, SVG · max 1MB</p>
      </div>
    </div>
  );
}
