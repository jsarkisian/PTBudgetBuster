const BASE_URL = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  // Health
  health: () => request('/health'),

  // Sessions
  createSession: (data) => request('/sessions', { method: 'POST', body: JSON.stringify(data) }),
  listSessions: () => request('/sessions'),
  getSession: (id) => request(`/sessions/${id}`),
  deleteSession: (id) => request(`/sessions/${id}`, { method: 'DELETE' }),

  // Tools
  listTools: () => request('/tools'),
  executeTool: (data) => request('/tools/execute', { method: 'POST', body: JSON.stringify(data) }),
  executeBash: (data) => request('/tools/execute/bash', { method: 'POST', body: JSON.stringify(data) }),

  // Tasks
  getTask: (id) => request(`/tasks/${id}`),
  killTask: (id) => request(`/tasks/${id}/kill`, { method: 'POST' }),

  // Chat
  chat: (data) => request('/chat', { method: 'POST', body: JSON.stringify(data) }),

  // Autonomous
  startAutonomous: (data) => request('/autonomous/start', { method: 'POST', body: JSON.stringify(data) }),
  stopAutonomous: (data) => request('/autonomous/stop', { method: 'POST', body: JSON.stringify(data) }),
  approveStep: (data) => request('/autonomous/approve', { method: 'POST', body: JSON.stringify(data) }),

  // Files
  listFiles: (dir = '') => request(`/files?directory=${encodeURIComponent(dir)}`),
  readFile: (path) => request(`/files/${path}`),

  // Export
  exportSession: (id) => {
    // Direct download - don't use request() since it returns a blob not JSON
    window.open(`${BASE_URL}/sessions/${id}/export`, '_blank');
  },
};
