const API_BASE = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  const token = localStorage.getItem("token");
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem("token");
    window.location.reload();
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

// Auth
export const login = (username, password) =>
  request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
export const getMe = () => request("/api/auth/me");
export const changePassword = (old_password, new_password) =>
  request("/api/auth/change-password", { method: "POST", body: JSON.stringify({ old_password, new_password }) });

// Engagements
export const createEngagement = (data) =>
  request("/api/engagements", { method: "POST", body: JSON.stringify(data) });
export const listEngagements = () => request("/api/engagements");
export const getEngagement = (id) => request(`/api/engagements/${id}`);
export const deleteEngagement = (id) =>
  request(`/api/engagements/${id}`, { method: "DELETE" });
export const startEngagement = (id) =>
  request(`/api/engagements/${id}/start`, { method: "POST" });
export const stopEngagement = (id) =>
  request(`/api/engagements/${id}/stop`, { method: "POST" });
export const getEngagementStatus = (id) =>
  request(`/api/engagements/${id}/status`);
export const approveExploitation = (id, findingIds) =>
  request(`/api/engagements/${id}/approve-exploitation`, {
    method: "POST", body: JSON.stringify({ finding_ids: findingIds }),
  });

// Findings
export const getFindings = (id) => request(`/api/engagements/${id}/findings`);
export const exportFindings = (id) => request(`/api/engagements/${id}/findings/export`);

// Events (historical log)
export const getEvents = (id) => request(`/api/engagements/${id}/events`);

// Chat (mid-run guidance)
export const sendMessage = (id, message) =>
  request(`/api/engagements/${id}/message`, { method: "POST", body: JSON.stringify({ message }) });

// Users (admin)
export const listUsers = () => request("/api/users");
export const createUser = (data) =>
  request("/api/users", { method: "POST", body: JSON.stringify(data) });
export const updateUser = (username, data) =>
  request(`/api/users/${username}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteUser = (username) =>
  request(`/api/users/${username}`, { method: "DELETE" });

// Health
export const getHealth = () => request("/api/health");
