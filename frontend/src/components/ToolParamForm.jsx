import React from 'react';

/**
 * Renders structured parameter inputs for a tool definition.
 * Supports: string (text), integer (number), boolean (checkbox), enum (radio buttons).
 *
 * Props:
 *   toolDef  – the tool definition object (has .parameters, .description, .risk_level)
 *   params   – current values dict  { paramKey: value }
 *   onChange – (key, value) => void
 */
export default function ToolParamForm({ toolDef, params, onChange }) {
  if (!toolDef) return null;
  const paramEntries = Object.entries(toolDef.parameters || {});
  if (paramEntries.length === 0) {
    return <p className="text-xs text-gray-500 italic">This tool has no configurable parameters.</p>;
  }

  return (
    <div className="space-y-3">
      {paramEntries.map(([key, pDef]) => (
        <ParamField key={key} name={key} def={pDef} value={params[key]} onChange={onChange} />
      ))}
    </div>
  );
}

function ParamField({ name, def, value, onChange }) {
  const label = (
    <div className="flex items-center gap-1.5 mb-1">
      <span className="text-xs font-mono text-gray-300">{name}</span>
      {def.required && <span className="text-accent-red text-xs">*</span>}
      <span className="text-xs text-gray-600">({def.type})</span>
      {def.flag && <span className="text-xs text-gray-600 font-mono">{def.flag}</span>}
    </div>
  );

  if (def.type === 'boolean') {
    return (
      <label className="flex items-start gap-2.5 cursor-pointer group">
        <input
          type="checkbox"
          checked={!!value}
          onChange={e => onChange(name, e.target.checked)}
          className="mt-0.5 rounded bg-dark-700 border-dark-500 accent-accent-blue"
        />
        <div>
          <span className="text-xs font-mono text-gray-300">{name}</span>
          {def.flag && <span className="text-xs text-gray-600 font-mono ml-1.5">{def.flag}</span>}
          {def.description && (
            <p className="text-xs text-gray-500 mt-0.5">{def.description}</p>
          )}
        </div>
      </label>
    );
  }

  if (def.type === 'enum' && def.options?.length) {
    return (
      <div>
        {label}
        <div className="flex flex-wrap gap-3">
          {def.options.map(opt => (
            <label key={opt} className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-300">
              <input
                type="radio"
                name={name}
                value={opt}
                checked={value === opt}
                onChange={() => onChange(name, opt)}
                className="accent-accent-blue"
              />
              {opt}
            </label>
          ))}
        </div>
        {def.description && <p className="text-xs text-gray-500 mt-1">{def.description}</p>}
      </div>
    );
  }

  if (def.type === 'integer') {
    return (
      <div>
        {label}
        <input
          type="number"
          value={value ?? ''}
          onChange={e => onChange(name, e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          placeholder={def.description}
          className="input text-xs"
        />
      </div>
    );
  }

  // Default: string
  return (
    <div>
      {label}
      <input
        type="text"
        value={value ?? ''}
        onChange={e => onChange(name, e.target.value)}
        placeholder={def.description}
        className="input text-xs"
      />
    </div>
  );
}
