import { useState, useEffect } from "react";
import {
  ArrowLeft, Plus, Trash2, Edit2, Shield, User, Check, X, Loader2,
  BookOpen, Upload, FileText,
} from "lucide-react";
import { listUsers, createUser, updateUser, deleteUser } from "../utils/api";
import {
  getFirmKnowledgeStatus, uploadFirmFindings, clearFirmFindings,
  getMethodology, saveMethodology, clearMethodology,
  uploadReportTemplate, clearReportTemplate,
} from "../utils/api";

const ROLES = ["admin", "operator", "viewer"];

function UserModal({ user, onSave, onClose }) {
  const isEdit = !!user;
  const [form, setForm] = useState({
    username: user?.username || "",
    password: "",
    display_name: user?.display_name || "",
    email: user?.email || "",
    role: user?.role || "operator",
    enabled: user?.enabled !== undefined ? user.enabled : true,
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!isEdit && (!form.username.trim() || !form.password.trim())) {
      setError("Username and password are required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (isEdit) {
        const payload = {
          display_name: form.display_name,
          email: form.email,
          role: form.role,
          enabled: form.enabled,
        };
        if (form.password.trim()) payload.password = form.password;
        await updateUser(user.username, payload);
      } else {
        await createUser({
          username: form.username.trim(),
          password: form.password,
          display_name: form.display_name.trim(),
          email: form.email.trim(),
          role: form.role,
        });
      }
      onSave();
    } catch (err) {
      setError(err.message || "Failed to save user");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-lg w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-base font-bold text-gray-100">
            {isEdit ? "Edit User" : "Create User"}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-3 py-2">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-1">Username</label>
            <input
              type="text"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              disabled={isEdit}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 disabled:text-gray-500 focus:outline-none focus:border-blue-500 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Password {isEdit && <span className="text-gray-600">(leave blank to keep current)</span>}
            </label>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Display Name</label>
            <input
              type="text"
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Role</label>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500 text-sm"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          {isEdit && (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="enabled"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
              />
              <label htmlFor="enabled" className="text-sm text-gray-300">Enabled</label>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-sm px-4 py-2 rounded-lg font-medium transition-colors"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              {isEdit ? "Save Changes" : "Create User"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function FirmKnowledge() {
  const [status, setStatus] = useState(null);
  const [methodology, setMethodology] = useState("");
  const [methodologySaving, setMethodologySaving] = useState(false);
  const [toast, setToast] = useState("");
  const [errors, setErrors] = useState({});

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(""), 3000); };
  const setErr = (key, msg) => setErrors((e) => ({ ...e, [key]: msg }));
  const clearErr = (key) => setErrors((e) => { const n = { ...e }; delete n[key]; return n; });

  const loadStatus = () =>
    getFirmKnowledgeStatus()
      .then(setStatus)
      .catch(() => {});

  useEffect(() => {
    loadStatus();
    getMethodology().then((d) => setMethodology(d.text || "")).catch(() => {});
  }, []);

  const handleFindingsUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    clearErr("findings");
    try {
      const result = await uploadFirmFindings(file);
      showToast(`${result.imported} findings imported`);
      loadStatus();
    } catch (err) {
      setErr("findings", err.message);
    }
    e.target.value = "";
  };

  const handleClearFindings = async () => {
    if (!confirm("Remove all firm findings?")) return;
    await clearFirmFindings().catch(() => {});
    showToast("Finding library cleared");
    loadStatus();
  };

  const handleSaveMethodology = async () => {
    setMethodologySaving(true);
    clearErr("methodology");
    try {
      await saveMethodology(methodology);
      showToast("Methodology saved");
      loadStatus();
    } catch (err) {
      setErr("methodology", err.message);
    } finally {
      setMethodologySaving(false);
    }
  };

  const handleClearMethodology = async () => {
    if (!confirm("Clear methodology?")) return;
    await clearMethodology().catch(() => {});
    setMethodology("");
    showToast("Methodology cleared");
    loadStatus();
  };

  const handleTemplateUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    clearErr("template");
    try {
      const result = await uploadReportTemplate(file);
      showToast(`Report template uploaded (${result.word_count.toLocaleString()} words)`);
      loadStatus();
    } catch (err) {
      setErr("template", err.message);
    }
    e.target.value = "";
  };

  const handleClearTemplate = async () => {
    if (!confirm("Remove report template?")) return;
    await clearReportTemplate().catch(() => {});
    showToast("Report template cleared");
    loadStatus();
  };

  const fmt = (iso) => iso ? new Date(iso).toLocaleDateString() : null;

  return (
    <div className="space-y-6">
      {toast && (
        <div className="bg-green-900/40 border border-green-700 text-green-300 text-sm rounded px-4 py-2">
          {toast}
        </div>
      )}

      {/* Finding Library */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-orange-400" />
            Finding Library
          </h3>
          {status?.findings?.count > 0 && (
            <span className="text-xs text-orange-400 bg-orange-900/30 border border-orange-800/50 px-2 py-0.5 rounded">
              {status.findings.count} findings loaded
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-3">
          CSV with columns: finding_title, description, recommendations, references, discussion_of_risk.
          {status?.findings?.updated_at && (
            <span className="ml-2 text-gray-600">Last updated: {fmt(status.findings.updated_at)}</span>
          )}
        </p>
        {errors.findings && (
          <p className="text-xs text-red-400 mb-2">{errors.findings}</p>
        )}
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm px-3 py-1.5 rounded cursor-pointer transition-colors">
            <Upload className="w-3.5 h-3.5" />
            Upload CSV
            <input type="file" accept=".csv" className="hidden" onChange={handleFindingsUpload} />
          </label>
          {status?.findings?.count > 0 && (
            <button
              onClick={handleClearFindings}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Clear
            </button>
          )}
          {(!status || status.findings.count === 0) && (
            <span className="text-xs text-gray-600">Not configured</span>
          )}
        </div>
      </div>

      {/* Methodology */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
            <FileText className="w-4 h-4 text-blue-400" />
            Methodology Document
          </h3>
          {status?.methodology?.configured && (
            <span className="text-xs text-gray-500">
              {status.methodology.char_count.toLocaleString()} chars
              {status.methodology.updated_at && ` · updated ${fmt(status.methodology.updated_at)}`}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Describe your firm's testing approach. Injected into the agent at the ANALYSIS phase.
        </p>
        {errors.methodology && (
          <p className="text-xs text-red-400 mb-2">{errors.methodology}</p>
        )}
        <textarea
          value={methodology}
          onChange={(e) => setMethodology(e.target.value)}
          placeholder="Our penetration testing methodology follows..."
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 resize-y min-h-[120px] focus:outline-none focus:border-blue-600"
        />
        <div className="flex items-center gap-2 mt-2">
          <button
            onClick={handleSaveMethodology}
            disabled={methodologySaving}
            className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm px-3 py-1.5 rounded transition-colors"
          >
            {methodologySaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            Save
          </button>
          {methodology && (
            <button
              onClick={handleClearMethodology}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Report Template */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
            <FileText className="w-4 h-4 text-purple-400" />
            Report Template
          </h3>
          {status?.report_template?.configured && (
            <span className="text-xs text-gray-500">
              {status.report_template.filename}
              {" · "}{status.report_template.word_count.toLocaleString()} words
              {status.report_template.updated_at && ` · updated ${fmt(status.report_template.updated_at)}`}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-3">
          Upload a .docx report. Text is extracted and used to guide the agent's finding narrative style.
          {!status?.report_template?.configured && (
            <span className="ml-1 text-gray-600">Not configured.</span>
          )}
        </p>
        {errors.template && (
          <p className="text-xs text-red-400 mb-2">{errors.template}</p>
        )}
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm px-3 py-1.5 rounded cursor-pointer transition-colors">
            <Upload className="w-3.5 h-3.5" />
            Upload .docx
            <input type="file" accept=".docx" className="hidden" onChange={handleTemplateUpload} />
          </label>
          {status?.report_template?.configured && (
            <button
              onClick={handleClearTemplate}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Feedback summary */}
      {status?.feedback?.count > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-gray-100 mb-1">Accumulated Feedback</h3>
          <p className="text-xs text-gray-500">
            {status.feedback.count} feedback entr{status.feedback.count !== 1 ? "ies" : "y"} collected from past scans.
            Injected into future ANALYSIS phases automatically.
          </p>
        </div>
      )}
    </div>
  );
}

export default function AdminPanel({ navigate }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modal, setModal] = useState(null); // null | "create" | user object
  const [deleting, setDeleting] = useState(null);
  const [tab, setTab] = useState("users");

  const fetchUsers = async () => {
    try {
      const data = await listUsers();
      setUsers(Array.isArray(data) ? data : data.users || []);
      setError("");
    } catch (err) {
      setError(err.message || "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleDelete = async (username) => {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    setDeleting(username);
    try {
      await deleteUser(username);
      setUsers((prev) => prev.filter((u) => u.username !== username));
    } catch (err) {
      setError(err.message || "Failed to delete user");
    } finally {
      setDeleting(null);
    }
  };

  const handleSave = () => {
    setModal(null);
    fetchUsers();
  };

  const roleIcon = (role) => {
    if (role === "admin") return <Shield className="w-3.5 h-3.5 text-orange-400" />;
    return <User className="w-3.5 h-3.5 text-gray-400" />;
  };

  return (
    <div className="max-w-5xl mx-auto p-6">
      <button
        onClick={() => navigate("dashboard")}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>

      <h2 className="text-xl font-bold text-gray-100 mb-6">Admin</h2>

      <div className="flex gap-1 mb-6 border-b border-gray-800">
        {[["users", "User Management"], ["firm", "Firm Knowledge"]].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === key
                ? "border-orange-500 text-orange-400"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-xl font-bold text-gray-100">User Management</h2>
              <p className="text-sm text-gray-400 mt-1">{users.length} user{users.length !== 1 ? "s" : ""}</p>
            </div>
            <button
              onClick={() => setModal("create")}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-medium transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create User
            </button>
          </div>

          {error && (
            <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-4 py-3 mb-4">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-20 text-gray-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Loading users...
            </div>
          ) : users.length === 0 ? (
            <div className="text-center py-20 text-gray-400">No users found.</div>
          ) : (
            <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800 text-gray-400 text-left">
                    <th className="px-4 py-3 font-medium">Username</th>
                    <th className="px-4 py-3 font-medium">Display Name</th>
                    <th className="px-4 py-3 font-medium">Role</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium w-24">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.username} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                      <td className="px-4 py-3 font-medium text-gray-100">{u.username}</td>
                      <td className="px-4 py-3 text-gray-400">{u.display_name || "--"}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1.5 text-gray-300">
                          {roleIcon(u.role)}
                          {u.role}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {u.enabled !== false ? (
                          <span className="text-green-400 text-xs font-medium">Active</span>
                        ) : (
                          <span className="text-red-400 text-xs font-medium">Disabled</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => setModal(u)}
                            className="p-1.5 text-gray-500 hover:text-blue-400 hover:bg-gray-700 rounded transition-colors"
                            title="Edit user"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(u.username)}
                            disabled={deleting === u.username}
                            className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
                            title="Delete user"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "firm" && <FirmKnowledge />}

      {/* Create / Edit Modal */}
      {modal !== null && (
        <UserModal
          user={modal === "create" ? null : modal}
          onSave={handleSave}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
