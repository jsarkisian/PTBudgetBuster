import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

const STATUS_COLORS = {
  scheduled: 'text-accent-blue',
  running: 'text-accent-yellow',
  completed: 'text-accent-green',
  failed: 'text-accent-red',
  disabled: 'text-gray-500',
};

const TYPE_COLORS = {
  once: 'bg-accent-cyan/20 text-accent-cyan',
  cron: 'bg-accent-purple/20 text-accent-purple',
};

export default function SchedulerPanel({ session, tools }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);

  // Create form state
  const [tool, setTool] = useState('');
  const [scheduleType, setScheduleType] = useState('once');
  const [runDate, setRunDate] = useState('');
  const [runTime, setRunTime] = useState('00:00');
  const [cronExpr, setCronExpr] = useState('');
  const [label, setLabel] = useState('');
  const [rawArgs, setRawArgs] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  // Edit state: { jobId } or null
  const [editingId, setEditingId] = useState(null);
  const [runningId, setRunningId] = useState(null);

  const loadJobs = async () => {
    if (!session) return;
    setLoading(true);
    try {
      const data = await api.listSchedules(session.id);
      setJobs(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to load schedules:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadJobs(); }, [session?.id]);

  const handleCreate = async () => {
    setFormError('');
    if (!tool) { setFormError('Select a tool'); return; }
    if (scheduleType === 'once' && !runDate) { setFormError('Enter run date/time'); return; }
    if (scheduleType === 'cron' && !cronExpr.trim()) { setFormError('Enter cron expression'); return; }

    setSubmitting(true);
    try {
      const runAtISO = scheduleType === 'once'
        ? new Date(`${runDate}T${runTime || '00:00'}`).toISOString()
        : undefined;
      const job = await api.createSchedule({
        session_id: session.id,
        tool,
        parameters: { __raw_args__: rawArgs.trim() },
        schedule_type: scheduleType,
        run_at: runAtISO,
        cron_expr: scheduleType === 'cron' ? cronExpr.trim() : undefined,
        label: label.trim(),
      });
      setJobs(prev => [...prev, job]);
      setShowForm(false);
      setTool(''); setLabel(''); setRunDate(''); setRunTime('00:00'); setCronExpr(''); setRawArgs('');
    } catch (e) {
      setFormError(e.message || 'Failed to create schedule');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    await api.deleteSchedule(id);
    setJobs(prev => prev.filter(j => j.id !== id));
    if (editingId === id) setEditingId(null);
  };

  const handleToggle = async (job) => {
    try {
      const updated = job.status === 'disabled'
        ? await api.enableSchedule(job.id)
        : await api.disableSchedule(job.id);
      setJobs(prev => prev.map(j => j.id === updated.id ? updated : j));
    } catch (e) {
      console.error('Failed to toggle schedule:', e);
    }
  };

  const handleRunNow = async (job) => {
    setRunningId(job.id);
    try {
      await api.runScheduleNow(job.id);
      // Poll briefly to pick up status change
      setTimeout(loadJobs, 1500);
    } catch (e) {
      console.error('Failed to run job:', e);
    } finally {
      setRunningId(null);
    }
  };

  const handleSaveEdit = (updatedJob) => {
    setJobs(prev => prev.map(j => j.id === updatedJob.id ? updatedJob : j));
    setEditingId(null);
  };

  const toolList = Object.keys(tools || {});
  const toolDef = tools?.[tool];

  return (
    <div className="h-full flex flex-col">
      <div className="panel-header shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-300">Scheduled Scans</span>
          <span className="text-xs text-gray-500">{jobs.length} job(s)</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadJobs} className="btn-ghost text-xs px-2 py-1">Refresh</button>
          <button onClick={() => setShowForm(!showForm)} className="btn-primary text-xs px-3 py-1">
            {showForm ? 'Cancel' : '+ Schedule Scan'}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="p-4 border-b border-dark-600 bg-dark-800 space-y-3">
          <h3 className="text-sm font-semibold text-gray-300">New Scheduled Scan</h3>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Tool *</label>
              <select value={tool} onChange={e => { setTool(e.target.value); setRawArgs(''); }} className="input text-xs w-full">
                <option value="">Select tool...</option>
                {toolList.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Label</label>
              <input value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g., Nightly recon" className="input text-xs w-full" />
            </div>
          </div>

          {tool && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Arguments
                <span className="text-gray-600 font-normal ml-2">— flags and values exactly as on the command line</span>
              </label>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-accent-cyan shrink-0">{tool}</span>
                <input
                  value={rawArgs}
                  onChange={e => setRawArgs(e.target.value)}
                  placeholder={buildPlaceholder(toolDef)}
                  className="input font-mono text-xs flex-1"
                />
              </div>
              {toolDef && <FlagHints toolDef={toolDef} />}
              {!rawArgs.trim() && session?.target_scope?.length > 0 && (
                <p className="mt-1 text-xs text-accent-blue/70">
                  No args — will target engagement scope: <span className="font-mono">{session.target_scope.join(', ')}</span>
                </p>
              )}
            </div>
          )}

          <div>
            <label className="block text-xs text-gray-400 mb-2">Schedule Type</label>
            <div className="flex gap-3">
              <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                <input type="radio" checked={scheduleType === 'once'} onChange={() => setScheduleType('once')} />
                One-time
              </label>
              <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                <input type="radio" checked={scheduleType === 'cron'} onChange={() => setScheduleType('cron')} />
                Recurring (cron)
              </label>
            </div>
          </div>

          {scheduleType === 'once' ? (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Run At *</label>
              <div className="flex gap-2">
                <input type="date" value={runDate} onChange={e => setRunDate(e.target.value)} className="input flex-1" />
                <input type="time" value={runTime} onChange={e => setRunTime(e.target.value)} className="input w-32" />
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Cron Expression *</label>
              <input value={cronExpr} onChange={e => setCronExpr(e.target.value)} placeholder="0 2 * * * (daily at 2am)" className="input text-xs font-mono w-full" />
              <p className="text-xs text-gray-600 mt-1">Format: minute hour day month weekday</p>
            </div>
          )}

          {formError && <p className="text-xs text-accent-red">{formError}</p>}

          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)} className="btn-ghost text-xs px-3 py-1">Cancel</button>
            <button onClick={handleCreate} disabled={submitting} className="btn-primary text-xs px-3 py-1">
              {submitting ? 'Scheduling...' : 'Schedule'}
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 bg-dark-950">
        {loading ? (
          <div className="text-center text-gray-600 text-xs py-8">Loading...</div>
        ) : jobs.length === 0 ? (
          <div className="text-center text-gray-600 text-xs py-8">
            No scheduled scans. Click "Schedule Scan" to create one.
          </div>
        ) : (
          <div className="space-y-2">
            {jobs.map(job => (
              <div key={job.id} className="bg-dark-800 border border-dark-600 rounded">
                {editingId === job.id ? (
                  <EditJobForm
                    job={job}
                    tools={tools}
                    session={session}
                    onSave={handleSaveEdit}
                    onCancel={() => setEditingId(null)}
                  />
                ) : (
                  <div className="p-3">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-sm text-accent-cyan">{job.tool}</span>
                          <span className={`text-[10px] px-1.5 rounded ${TYPE_COLORS[job.schedule_type] || ''}`}>
                            {job.schedule_type}
                          </span>
                          <span className={`text-xs ${STATUS_COLORS[job.status] || 'text-gray-400'}`}>
                            {job.status}
                          </span>
                        </div>
                        {job.label && <p className="text-xs text-gray-300 mb-1">{job.label}</p>}
                        <div className="text-xs text-gray-500 space-y-0.5">
                          {job.parameters?.__raw_args__ && (
                            <div className="font-mono text-gray-400">{job.tool} {job.parameters.__raw_args__}</div>
                          )}
                          {job.schedule_type === 'once' && job.run_at && (
                            <div>Run at: {new Date(job.run_at).toLocaleString()}</div>
                          )}
                          {job.schedule_type === 'cron' && (
                            <div>Cron: <span className="font-mono text-gray-400">{job.cron_expr}</span></div>
                          )}
                          {job.last_run && <div>Last run: {new Date(job.last_run).toLocaleString()}</div>}
                          <div>Run count: {job.run_count}</div>
                          {job.created_by && <div>Created by: {job.created_by}</div>}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 ml-3 shrink-0">
                        {/* Run Now */}
                        <button
                          onClick={() => handleRunNow(job)}
                          disabled={runningId === job.id}
                          className="text-xs btn-ghost px-2 py-1 text-accent-green"
                          title="Run now"
                        >
                          {runningId === job.id ? '…' : '▶▶'}
                        </button>
                        {/* Edit */}
                        <button
                          onClick={() => setEditingId(job.id)}
                          className="text-xs btn-ghost px-2 py-1"
                          title="Edit"
                        >
                          ✎
                        </button>
                        {/* Enable/Disable */}
                        {job.status !== 'completed' && (
                          <button
                            onClick={() => handleToggle(job)}
                            className="text-xs btn-ghost px-2 py-1"
                            title={job.status === 'disabled' ? 'Enable' : 'Disable'}
                          >
                            {job.status === 'disabled' ? '▶' : '⏸'}
                          </button>
                        )}
                        {/* Delete */}
                        <button onClick={() => handleDelete(job.id)} className="text-xs text-gray-500 hover:text-accent-red px-1">✕</button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Inline edit form
// ─────────────────────────────────────────────────────────────
function EditJobForm({ job, tools, session, onSave, onCancel }) {
  const [tool, setTool] = useState(job.tool);
  const [rawArgs, setRawArgs] = useState(job.parameters?.__raw_args__ || '');
  const [label, setLabel] = useState(job.label || '');
  const [scheduleType, setScheduleType] = useState(job.schedule_type);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Parse run_at into date + time strings
  const parseRunAt = (iso) => {
    if (!iso) return { date: '', time: '00:00' };
    const d = new Date(iso);
    const date = d.toLocaleDateString('en-CA'); // YYYY-MM-DD
    const time = d.toTimeString().slice(0, 5);   // HH:MM
    return { date, time };
  };
  const parsed = parseRunAt(job.run_at);
  const [runDate, setRunDate] = useState(parsed.date);
  const [runTime, setRunTime] = useState(parsed.time);
  const [cronExpr, setCronExpr] = useState(job.cron_expr || '');

  const toolDef = tools?.[tool];
  const toolList = Object.keys(tools || {});

  const handleSave = async () => {
    setError('');
    if (!tool) { setError('Select a tool'); return; }
    if (scheduleType === 'once' && !runDate) { setError('Enter run date'); return; }
    if (scheduleType === 'cron' && !cronExpr.trim()) { setError('Enter cron expression'); return; }

    setSaving(true);
    try {
      const run_at = scheduleType === 'once'
        ? new Date(`${runDate}T${runTime || '00:00'}`).toISOString()
        : null;
      const updated = await api.updateSchedule(job.id, {
        tool,
        parameters: { __raw_args__: rawArgs.trim() },
        label: label.trim(),
        schedule_type: scheduleType,
        run_at: scheduleType === 'once' ? run_at : null,
        cron_expr: scheduleType === 'cron' ? cronExpr.trim() : null,
      });
      onSave(updated);
    } catch (e) {
      setError(e.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-3 space-y-3">
      <h4 className="text-xs font-semibold text-gray-300">Edit Scheduled Scan</h4>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Tool</label>
          <select value={tool} onChange={e => { setTool(e.target.value); setRawArgs(''); }} className="input text-xs w-full">
            {toolList.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Label</label>
          <input value={label} onChange={e => setLabel(e.target.value)} className="input text-xs w-full" />
        </div>
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1">
          Arguments
        </label>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-accent-cyan shrink-0">{tool}</span>
          <input
            value={rawArgs}
            onChange={e => setRawArgs(e.target.value)}
            placeholder={buildPlaceholder(toolDef)}
            className="input font-mono text-xs flex-1"
          />
        </div>
        {toolDef && <FlagHints toolDef={toolDef} />}
        {!rawArgs.trim() && session?.target_scope?.length > 0 && (
          <p className="mt-1 text-xs text-accent-blue/70">
            No args — will target engagement scope: <span className="font-mono">{session.target_scope.join(', ')}</span>
          </p>
        )}
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-2">Schedule Type</label>
        <div className="flex gap-3">
          <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
            <input type="radio" checked={scheduleType === 'once'} onChange={() => setScheduleType('once')} />
            One-time
          </label>
          <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
            <input type="radio" checked={scheduleType === 'cron'} onChange={() => setScheduleType('cron')} />
            Recurring (cron)
          </label>
        </div>
      </div>

      {scheduleType === 'once' ? (
        <div>
          <label className="block text-xs text-gray-400 mb-1">Run At</label>
          <div className="flex gap-2">
            <input type="date" value={runDate} onChange={e => setRunDate(e.target.value)} className="input flex-1" />
            <input type="time" value={runTime} onChange={e => setRunTime(e.target.value)} className="input w-32" />
          </div>
        </div>
      ) : (
        <div>
          <label className="block text-xs text-gray-400 mb-1">Cron Expression</label>
          <input value={cronExpr} onChange={e => setCronExpr(e.target.value)} placeholder="0 2 * * *" className="input text-xs font-mono w-full" />
          <p className="text-xs text-gray-600 mt-1">Format: minute hour day month weekday</p>
        </div>
      )}

      {error && <p className="text-xs text-accent-red">{error}</p>}

      <div className="flex justify-end gap-2">
        <button onClick={onCancel} className="btn-ghost text-xs px-3 py-1">Cancel</button>
        <button onClick={handleSave} disabled={saving} className="btn-primary text-xs px-3 py-1">
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────────────────────
function buildPlaceholder(toolDef) {
  if (!toolDef?.parameters) return 'e.g., -u https://example.com';
  const parts = [];
  for (const [, pDef] of Object.entries(toolDef.parameters).slice(0, 3)) {
    if (pDef.flag && pDef.description) {
      parts.push(`${pDef.flag} <${pDef.description.split(' ').slice(0, 2).join('-').toLowerCase()}>`);
    }
  }
  return parts.length ? parts.join(' ') : 'e.g., -u https://example.com';
}

function FlagHints({ toolDef }) {
  const [open, setOpen] = React.useState(false);
  const params = Object.entries(toolDef?.parameters || {});
  if (!params.length) return null;

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="text-xs text-gray-600 hover:text-gray-400 underline"
      >
        {open ? 'Hide' : 'Show'} available flags
      </button>
      {open && (
        <div className="mt-1 p-2 bg-dark-900 border border-dark-600 rounded space-y-1">
          {params.map(([name, pDef]) => (
            <div key={name} className="flex gap-2 text-xs">
              <span className="font-mono text-accent-cyan shrink-0 w-24">{pDef.flag || name}</span>
              <span className="text-gray-500">{pDef.description}</span>
              {pDef.required && <span className="text-accent-red shrink-0">required</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
