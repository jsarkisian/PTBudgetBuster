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
  sendAutoMessage: (data) => request('/autonomous/message', { method: 'POST', body: JSON.stringify(data) }),

  // Files
  listFiles: (dir = '') => request(`/files?directory=${encodeURIComponent(dir)}`),
  readFile: (path) => request(`/files/${path}`),

  // Export
  exportSession: (id) => {
    const url = `${BASE_URL}/sessions/${id}/export`;
    fetch(url, {
      headers: authToken ? { 'Authorization': `Bearer ${authToken}` } : {},
    })
      .then(res => {
        const disposition = res.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^";\n]+)"?/);
        const filename = match ? match[1].trim() : `engagement_${id}_export.zip`;
        return res.blob().then(blob => ({ blob, filename }));
      })
      .then(({ blob, filename }) => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
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

  // Settings / Branding
  getLogo: () => request('/settings/logo'),
  setLogo: (logo) => request('/settings/logo', { method: 'POST', body: JSON.stringify({ logo }) }),
  deleteLogo: () => request('/settings/logo', { method: 'DELETE' }),

  // Screenshots
  listScreenshots: (dir = '') => request(`/screenshots?directory=${encodeURIComponent(dir)}`),

  // Clients
  listClients: () => request('/clients'),
  createClient: (data) => request('/clients', { method: 'POST', body: JSON.stringify(data) }),
  getClient: (id) => request(`/clients/${id}`),
  updateClient: (id, data) => request(`/clients/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteClient: (id) => request(`/clients/${id}`, { method: 'DELETE' }),
  addAsset: (clientId, data) => request(`/clients/${clientId}/assets`, { method: 'POST', body: JSON.stringify(data) }),
  removeAsset: (clientId, assetId) => request(`/clients/${clientId}/assets/${assetId}`, { method: 'DELETE' }),

  // Schedules
  listSchedules: (sessionId = null) => request(`/schedules${sessionId ? `?session_id=${sessionId}` : ''}`),
  createSchedule: (data) => request('/schedules', { method: 'POST', body: JSON.stringify(data) }),
  getSchedule: (id) => request(`/schedules/${id}`),
  deleteSchedule: (id) => request(`/schedules/${id}`, { method: 'DELETE' }),
  disableSchedule: (id) => request(`/schedules/${id}/disable`, { method: 'POST' }),
  enableSchedule: (id) => request(`/schedules/${id}/enable`, { method: 'POST' }),
  updateSchedule: (id, data) => request(`/schedules/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  runScheduleNow: (id) => request(`/schedules/${id}/run`, { method: 'POST' }),

  // Tool Management
  getToolDefinitions: () => request('/tools/definitions'),
  addToolDefinition: (data) => request('/tools/definitions', { method: 'POST', body: JSON.stringify(data) }),
  updateToolDefinition: (name, data) => request(`/tools/definitions/${name}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteToolDefinition: (name) => request(`/tools/definitions/${name}`, { method: 'DELETE' }),
  checkToolInstalled: (binary) => request('/tools/check', { method: 'POST', body: JSON.stringify({ binary }) }),
  updateTool: (tool) => request('/tools/update', { method: 'POST', body: JSON.stringify({ tool }) }),
  installGoTool: (pkg) => request('/tools/install-go', { method: 'POST', body: JSON.stringify({ package: pkg }) }),
  installAptTool: (pkg) => request('/tools/install-apt', { method: 'POST', body: JSON.stringify({ package: pkg }) }),
  installGitTool: (repo, installCmd) => request('/tools/install-git', { method: 'POST', body: JSON.stringify({ repo, install_cmd: installCmd }) }),
  installPipTool: (pkg) => request('/tools/install-pip', { method: 'POST', body: JSON.stringify({ package: pkg }) }),
};
