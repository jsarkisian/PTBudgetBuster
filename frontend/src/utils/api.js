const BASE_URL = '/api';

let authToken = localStorage.getItem('auth_token') || null;

export function setToken(token) {
  authToken = token;
  if (token) {
    localStorage.setItem('auth_token', token);
  } else {
    localStorage.removeItem('auth_token');
  }
}

export function getToken() {
  return authToken;
}

export function isAuthenticated() {
  return !!authToken;
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }
  const res = await fetch(`${BASE_URL}${path}`, { headers, ...options });
  if (res.status === 401) {
    setToken(null);
    window.location.reload();
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  // Auth
  login: (username, password) => request('/auth/login', {
    method: 'POST', body: JSON.stringify({ username, password }),
  }),
  getMe: () => request('/auth/me'),
  changePassword: (current_password, new_password) => request('/auth/change-password', {
    method: 'POST', body: JSON.stringify({ current_password, new_password }),
  }),

  // Health
  health: () => request('/health'),

  // Sessions
  createSession: (data) => request('/sessions', { method: 'POST', body: JSON.stringify(data) }),
  listSessions: () => request('/sessions'),
  getSession: (id) => request(`/sessions/${id}`),
  deleteSession: (id) => request(`/sessions/${id}`, { method: 'DELETE' }),
  updateSession: (id, data) => request(`/sessions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Tools
  listTools: () => request('/tools'),
  executeTool: (data) => request('/tools/execute', { method: 'POST', body: JSON.stringify(data) }),
  executeBash: (data) => request('/tools/execute/bash', { method: 'POST', body: JSON.stringify(data) }),

  // Tasks
  getTask: (id) => request(`/tasks/${id}`),
  killTask: (id) => request(`/tasks/${id}/kill`, { method: 'POST' }),

  // Chat
  chat: (data, signal) => request('/chat', { method: 'POST', body: JSON.stringify(data), signal }),

  // Autonomous
  startAutonomous: (data) => request('/autonomous/start', { method: 'POST', body: JSON.stringify(data) }),
  stopAutonomous: (data) => request('/autonomous/stop', { method: 'POST', body: JSON.stringify(data) }),
  approveStep: (data) => request('/autonomous/approve', { method: 'POST', body: JSON.stringify(data) }),

  // Files
  listFiles: (dir = '') => request(`/files?directory=${encodeURIComponent(dir)}`),
  readFile: (path) => request(`/files/${path}`),

  // Export
  exportSession: (id) => {
    const url = `${BASE_URL}/sessions/${id}/export`;
    // Add auth header via fetch for download
    fetch(url, {
      headers: authToken ? { 'Authorization': `Bearer ${authToken}` } : {},
    })
      .then(res => res.blob())
      .then(blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `engagement_export.zip`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
  },

  // Users (admin)
  listUsers: () => request('/users'),
  createUser: (data) => request('/users', { method: 'POST', body: JSON.stringify(data) }),
  getUser: (username) => request(`/users/${username}`),
  updateUser: (username, data) => request(`/users/${username}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteUser: (username) => request(`/users/${username}`, { method: 'DELETE' }),
  resetPassword: (username, new_password) => request(`/users/${username}/reset-password`, {
    method: 'POST', body: JSON.stringify({ new_password }),
  }),

  // SSH Keys
  listSSHKeys: (username) => request(`/users/${username}/ssh-keys`),
  addSSHKey: (username, name, pubkey) => request(`/users/${username}/ssh-keys`, {
    method: 'POST', body: JSON.stringify({ name, pubkey }),
  }),
  removeSSHKey: (username, keyId) => request(`/users/${username}/ssh-keys/${keyId}`, { method: 'DELETE' }),
};
