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

  // Form state
  const [tool, setTool] = useState('');
  const [scheduleType, setScheduleType] = useState('once');
  const [runAt, setRunAt] = useState('');
  const [cronExpr, setCronExpr] = useState('');
  const [label, setLabel] = useState('');
  const [params, setParams] = useState('{}');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

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
    if (scheduleType === 'once' && !runAt) { setFormError('Enter run date/time'); return; }
    if (scheduleType === 'cron' && !cronExpr.trim()) { setFormError('Enter cron expression'); return; }

    let parsedParams = {};
    try {
      parsedParams = JSON.parse(params);
    } catch {
      setFormError('Parameters must be valid JSON');
      return;
    }

    setSubmitting(true);
    try {
      const job = await api.createSchedule({
        session_id: session.id,
        tool,
        parameters: parsedParams,
        schedule_type: scheduleType,
        run_at: scheduleType === 'once' ? new Date(runAt).toISOString() : undefined,
        cron_expr: scheduleType === 'cron' ? cronExpr.trim() : undefined,
        label: label.trim(),
      });
      setJobs(prev => [...prev, job]);
      setShowForm(false);
      setTool(''); setLabel(''); setRunAt(''); setCronExpr(''); setParams('{}');
    } catch (e) {
      setFormError(e.message || 'Failed to create schedule');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    await api.deleteSchedule(id);
    setJobs(prev => prev.filter(j => j.id !== id));
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

  const toolList = Object.keys(tools || {});

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
              <select value={tool} onChange={e => setTool(e.target.value)} className="input text-xs w-full">
                <option value="">Select tool...</option>
                {toolList.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Label</label>
              <input value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g., Nightly recon" className="input text-xs w-full" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">Parameters (JSON)</label>
            <input value={params} onChange={e => setParams(e.target.value)} placeholder='{"target": "example.com"}' className="input text-xs font-mono w-full" />
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
              <label className="block text-xs text-gray-400 mb-1">Run At *</label>
              <input type="datetime-local" value={runAt} onChange={e => setRunAt(e.target.value)} className="input" />
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
              <div key={job.id} className="bg-dark-800 border border-dark-600 rounded p-3">
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
                  <div className="flex items-center gap-2 ml-3">
                    {job.status !== 'completed' && (
                      <button
                        onClick={() => handleToggle(job)}
                        className="text-xs btn-ghost px-2 py-1"
                        title={job.status === 'disabled' ? 'Enable' : 'Disable'}
                      >
                        {job.status === 'disabled' ? '▶' : '⏸'}
                      </button>
                    )}
                    <button onClick={() => handleDelete(job.id)} className="text-xs text-gray-500 hover:text-accent-red px-1">✕</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
