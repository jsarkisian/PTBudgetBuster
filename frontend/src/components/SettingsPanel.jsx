import React, { useState, useEffect, useRef } from 'react';
import { api } from '../utils/api';
import PlaybookManager from './PlaybookManager';

export default function SettingsPanel({ logoUrl, onLogoChange, fontSize, onFontSizeChange }) {
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

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <BrandingSection logoUrl={logoUrl} onLogoChange={onLogoChange} onFlash={flash} onError={setError} />
        <FontSizeSection fontSize={fontSize} onFontSizeChange={onFontSizeChange} onFlash={flash} onError={setError} />

        {/* Playbooks section */}
        <div className="mt-6 border-t border-gray-700 pt-6">
          <PlaybookManager />
        </div>
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
        <div className="w-16 h-16 flex items-center justify-center bg-dark-800 border border-dark-600 rounded-lg shrink-0">
          {preview
            ? <img src={preview} alt="Logo" className="w-14 h-14 object-contain rounded" />
            : <span className="text-3xl">🛡️</span>
          }
        </div>
        <div className="flex flex-col gap-2">
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
          <p className="text-xs text-gray-600">PNG, JPG, SVG -- max 1MB</p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>
    </div>
  );
}

function FontSizeSection({ fontSize, onFontSizeChange, onFlash, onError }) {
  const options = [
    { value: 'small', label: 'Small', px: '14px' },
    { value: 'default', label: 'Default', px: '16px' },
    { value: 'large', label: 'Large', px: '18px' },
    { value: 'x-large', label: 'Extra Large', px: '20px' },
  ];

  const handleChange = async (size) => {
    onFontSizeChange(size);
    try {
      await api.setFontSize(size);
      onFlash('Font size updated');
    } catch (err) {
      onError(err.message);
    }
  };

  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Font Size</h3>
      <div className="flex gap-2">
        {options.map(opt => (
          <button
            key={opt.value}
            onClick={() => handleChange(opt.value)}
            className={`px-4 py-2 rounded text-xs font-medium border transition-colors ${
              fontSize === opt.value
                ? 'bg-accent-blue/20 border-accent-blue/50 text-accent-blue'
                : 'bg-dark-800 border-dark-600 text-gray-400 hover:bg-dark-700 hover:text-gray-300'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-600 mt-2">
        Applies to all users. Current: {options.find(o => o.value === fontSize)?.px || '16px'}
      </p>
    </div>
  );
}
