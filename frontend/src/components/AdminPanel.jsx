import React, { useState, useEffect, useRef } from 'react';
import { api } from '../utils/api';

export default function AdminPanel({ currentUser, logoUrl, onLogoChange }) {
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [showAddKey, setShowAddKey] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isAdmin = currentUser?.role === 'admin';

  useEffect(() => {
    if (isAdmin) {
      loadUsers();
    }
  }, [isAdmin]);

  const loadUsers = async () => {
    try {
      const data = await api.listUsers();
      setUsers(data);
    } catch (err) {
      setError(err.message);
    }
  };

  const flash = (msg) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(''), 3000);
  };

  if (!isAdmin) {
    return (
      <div className="h-full flex flex-col">
        <div className="panel-header">
          <span className="text-sm font-semibold text-gray-300">My Account</span>
        </div>
        <div className="flex-1 p-4">
          <MyAccountPanel currentUser={currentUser} />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="panel-header">
        <span className="text-sm font-semibold text-gray-300">User Management</span>
        <button onClick={() => setShowCreateUser(true)} className="btn-primary text-xs px-3 py-1">
          + Add User
        </button>
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

      <div className="flex-1 flex overflow-hidden">
        {/* User list */}
        <div className="w-64 border-r border-dark-600 overflow-y-auto">
          {users.map(user => (
            <div
              key={user.id}
              onClick={() => setSelectedUser(user)}
              className={`px-4 py-3 cursor-pointer border-b border-dark-700 transition-colors ${
                selectedUser?.username === user.username
                  ? 'bg-dark-700'
                  : 'hover:bg-dark-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-200">{user.display_name || user.username}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                  user.role === 'admin' ? 'bg-accent-red/20 text-accent-red' :
                  user.role === 'operator' ? 'bg-accent-blue/20 text-accent-blue' :
                  'bg-gray-600/20 text-gray-400'
                }`}>
                  {user.role}
                </span>
              </div>
              <div className="text-xs text-gray-500 mt-0.5">@{user.username}</div>
              <div className="flex items-center gap-2 mt-1">
                {!user.enabled && (
                  <span className="text-[10px] bg-red-500/20 text-red-400 px-1.5 rounded">disabled</span>
                )}
                {user.ssh_keys?.length > 0 && (
                  <span className="text-[10px] text-gray-500">🔑 {user.ssh_keys.length}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* User detail */}
        <div className="flex-1 overflow-y-auto p-4">
          {selectedUser ? (
            <UserDetail
              user={selectedUser}
              onUpdate={() => { loadUsers(); }}
              onFlash={flash}
              onError={setError}
              showAddKey={showAddKey}
              setShowAddKey={setShowAddKey}
            />
          ) : (
            <div className="text-center text-gray-500 text-sm py-12">
              Select a user to manage
            </div>
          )}
          <BrandingSection logoUrl={logoUrl} onLogoChange={onLogoChange} onFlash={flash} onError={setError} />
        </div>
      </div>

      {showCreateUser && (
        <CreateUserModal
          onClose={() => setShowCreateUser(false)}
          onCreate={() => { loadUsers(); setShowCreateUser(false); flash('User created'); }}
          onError={setError}
        />
      )}

    </div>
  );
}

function MyAccountPanel({ currentUser }) {
  const [sshKeys, setSSHKeys] = useState([]);
  const [showAddKey, setShowAddKey] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [keyValue, setKeyValue] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => { loadKeys(); }, []);

  const loadKeys = async () => {
    try {
      const keys = await api.listSSHKeys(currentUser.username);
      setSSHKeys(keys);
    } catch {}
  };

  const handleAddKey = async () => {
    setError('');
    try {
      await api.addSSHKey(currentUser.username, keyName, keyValue);
      setKeyName('');
      setKeyValue('');
      setShowAddKey(false);
      setSuccess('SSH key added');
      setTimeout(() => setSuccess(''), 3000);
      loadKeys();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleRemoveKey = async (keyId) => {
    try {
      await api.removeSSHKey(currentUser.username, keyId);
      loadKeys();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h3 className="text-sm font-semibold text-gray-200 mb-2">Account Info</h3>
        <div className="bg-dark-800 border border-dark-600 rounded p-4 text-sm space-y-2">
          <div><span className="text-gray-500">Username:</span> <span className="text-gray-200">{currentUser.username}</span></div>
          <div><span className="text-gray-500">Role:</span> <span className="text-gray-200">{currentUser.role}</span></div>
          <div><span className="text-gray-500">Display Name:</span> <span className="text-gray-200">{currentUser.display_name}</span></div>
        </div>
      </div>

      {error && <div className="bg-red-500/10 border border-red-500/30 rounded px-3 py-2 text-xs text-red-400">{error}</div>}
      {success && <div className="bg-green-500/10 border border-green-500/30 rounded px-3 py-2 text-xs text-green-400">{success}</div>}

      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-200">My SSH Keys</h3>
          <button onClick={() => setShowAddKey(true)} className="btn-primary text-xs px-3 py-1">+ Add Key</button>
        </div>
        <SSHKeyList keys={sshKeys} onRemove={handleRemoveKey} />
      </div>

      {showAddKey && (
        <AddKeyForm
          keyName={keyName} setKeyName={setKeyName}
          keyValue={keyValue} setKeyValue={setKeyValue}
          onSubmit={handleAddKey}
          onCancel={() => setShowAddKey(false)}
          error={error}
        />
      )}

      <ChangePasswordForm username={currentUser.username} />
    </div>
  );
}

function UserDetail({ user, onUpdate, onFlash, onError, showAddKey, setShowAddKey }) {
  const [keyName, setKeyName] = useState('');
  const [keyValue, setKeyValue] = useState('');
  const [showResetPw, setShowResetPw] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const handleToggleEnabled = async () => {
    try {
      await api.updateUser(user.username, { enabled: !user.enabled });
      onFlash(user.enabled ? 'User disabled' : 'User enabled');
      onUpdate();
    } catch (err) {
      onError(err.message);
    }
  };

  const handleChangeRole = async (role) => {
    try {
      await api.updateUser(user.username, { role });
      onFlash(`Role changed to ${role}`);
      onUpdate();
    } catch (err) {
      onError(err.message);
    }
  };

  const handleResetPassword = async () => {
    try {
      await api.resetPassword(user.username, newPassword);
      setNewPassword('');
      setShowResetPw(false);
      onFlash('Password reset');
    } catch (err) {
      onError(err.message);
    }
  };

  const handleDeleteUser = async () => {
    try {
      await api.deleteUser(user.username);
      setShowDeleteConfirm(false);
      onFlash('User deleted');
      onUpdate();
    } catch (err) {
      onError(err.message);
    }
  };

  const handleAddKey = async () => {
    try {
      await api.addSSHKey(user.username, keyName, keyValue);
      setKeyName('');
      setKeyValue('');
      setShowAddKey(false);
      onFlash('SSH key added');
      onUpdate();
    } catch (err) {
      onError(err.message);
    }
  };

  const handleRemoveKey = async (keyId) => {
    try {
      await api.removeSSHKey(user.username, keyId);
      onFlash('SSH key removed');
      onUpdate();
    } catch (err) {
      onError(err.message);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* User info */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">{user.display_name || user.username}</h2>
          <p className="text-sm text-gray-500">@{user.username} · {user.email || 'No email'}</p>
          <p className="text-xs text-gray-600 mt-1">Created: {new Date(user.created_at).toLocaleDateString()}</p>
          {user.last_login && <p className="text-xs text-gray-600">Last login: {new Date(user.last_login).toLocaleString()}</p>}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleToggleEnabled}
            className={`text-xs px-3 py-1.5 rounded border transition-colors ${
              user.enabled
                ? 'border-accent-yellow/30 text-accent-yellow hover:bg-accent-yellow/10'
                : 'border-accent-green/30 text-accent-green hover:bg-accent-green/10'
            }`}
          >
            {user.enabled ? 'Disable' : 'Enable'}
          </button>
          {user.username !== 'admin' && (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="text-xs px-3 py-1.5 rounded border border-accent-red/30 text-accent-red hover:bg-accent-red/10 transition-colors"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Role */}
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Role</h3>
        <div className="flex gap-2">
          {['admin', 'operator', 'viewer'].map(role => (
            <button
              key={role}
              onClick={() => handleChangeRole(role)}
              className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                user.role === role
                  ? 'border-accent-blue bg-accent-blue/20 text-accent-blue'
                  : 'border-dark-500 text-gray-400 hover:border-gray-400'
              }`}
            >
              {role}
            </button>
          ))}
        </div>
      </div>

      {/* Password reset */}
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Password</h3>
        {showResetPw ? (
          <div className="flex gap-2">
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="New password"
              className="flex-1 px-3 py-1.5 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
            />
            <button onClick={handleResetPassword} className="btn-primary text-xs px-3">Reset</button>
            <button onClick={() => setShowResetPw(false)} className="btn-ghost text-xs px-3">Cancel</button>
          </div>
        ) : (
          <button onClick={() => setShowResetPw(true)} className="btn-ghost text-xs px-3 py-1.5">
            Reset Password
          </button>
        )}
      </div>

      {/* SSH Keys */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-300">SSH Keys</h3>
          <button onClick={() => setShowAddKey(true)} className="btn-primary text-xs px-3 py-1">+ Add Key</button>
        </div>

        {showAddKey && (
          <AddKeyForm
            keyName={keyName} setKeyName={setKeyName}
            keyValue={keyValue} setKeyValue={setKeyValue}
            onSubmit={handleAddKey}
            onCancel={() => setShowAddKey(false)}
          />
        )}

        <SSHKeyList keys={user.ssh_keys || []} onRemove={handleRemoveKey} />
      </div>

      {/* Delete confirm */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-dark-800 border border-dark-500 rounded-lg p-5 max-w-sm">
            <div className="text-lg font-semibold text-gray-200 mb-2">Delete User?</div>
            <p className="text-sm text-gray-400 mb-4">
              Permanently delete <span className="text-gray-200 font-medium">@{user.username}</span>?
              Their SSH keys will also be removed from the server.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowDeleteConfirm(false)} className="px-4 py-2 text-sm text-gray-300 bg-dark-700 hover:bg-dark-600 rounded border border-dark-500">Cancel</button>
              <button onClick={handleDeleteUser} className="px-4 py-2 text-sm text-white bg-red-600 hover:bg-red-500 rounded">Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SSHKeyList({ keys, onRemove }) {
  if (keys.length === 0) {
    return <div className="text-xs text-gray-500 py-3">No SSH keys configured</div>;
  }

  return (
    <div className="space-y-2">
      {keys.map(key => (
        <div key={key.id} className="bg-dark-800 border border-dark-600 rounded px-3 py-2 flex items-center justify-between">
          <div>
            <div className="text-sm text-gray-200 font-medium">🔑 {key.name}</div>
            <div className="text-xs text-gray-500 font-mono mt-0.5">{key.fingerprint}</div>
            <div className="text-[10px] text-gray-600 mt-0.5">Added: {new Date(key.added_at).toLocaleDateString()}</div>
          </div>
          <button
            onClick={() => onRemove(key.id)}
            className="text-gray-500 hover:text-accent-red text-base p-1 transition-colors"
            title="Remove key"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

function AddKeyForm({ keyName, setKeyName, keyValue, setKeyValue, onSubmit, onCancel, error }) {
  return (
    <div className="bg-dark-800 border border-dark-600 rounded p-4 mb-3 space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">Key Name</label>
        <input
          type="text"
          value={keyName}
          onChange={(e) => setKeyName(e.target.value)}
          placeholder="e.g., Work Laptop, MacBook"
          className="w-full px-3 py-1.5 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">Public Key</label>
        <textarea
          value={keyValue}
          onChange={(e) => setKeyValue(e.target.value)}
          placeholder="ssh-ed25519 AAAA... user@host"
          rows={3}
          className="w-full px-3 py-1.5 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 font-mono focus:border-accent-blue focus:outline-none resize-none"
        />
      </div>
      {error && <div className="text-xs text-red-400">{error}</div>}
      <div className="flex gap-2">
        <button onClick={onSubmit} className="btn-primary text-xs px-4 py-1.5">Add Key</button>
        <button onClick={onCancel} className="btn-ghost text-xs px-4 py-1.5">Cancel</button>
      </div>
    </div>
  );
}

function ChangePasswordForm() {
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleSubmit = async () => {
    setError('');
    if (newPw !== confirmPw) {
      setError('Passwords do not match');
      return;
    }
    if (newPw.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }
    try {
      await api.changePassword(currentPw, newPw);
      setCurrentPw('');
      setNewPw('');
      setConfirmPw('');
      setSuccess('Password changed');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-200 mb-2">Change Password</h3>
      <div className="bg-dark-800 border border-dark-600 rounded p-4 space-y-3 max-w-sm">
        <input
          type="password"
          value={currentPw}
          onChange={(e) => setCurrentPw(e.target.value)}
          placeholder="Current password"
          className="w-full px-3 py-1.5 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
        />
        <input
          type="password"
          value={newPw}
          onChange={(e) => setNewPw(e.target.value)}
          placeholder="New password"
          className="w-full px-3 py-1.5 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
        />
        <input
          type="password"
          value={confirmPw}
          onChange={(e) => setConfirmPw(e.target.value)}
          placeholder="Confirm new password"
          className="w-full px-3 py-1.5 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
        />
        {error && <div className="text-xs text-red-400">{error}</div>}
        {success && <div className="text-xs text-green-400">{success}</div>}
        <button onClick={handleSubmit} className="btn-primary text-xs px-4 py-1.5">Change Password</button>
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
    <div className="border-t border-dark-600 px-4 py-4">
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

function CreateUserModal({ onClose, onCreate, onError }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('operator');
  const [error, setError] = useState('');

  const handleCreate = async () => {
    setError('');
    if (!username || !password) {
      setError('Username and password are required');
      return;
    }
    try {
      await api.createUser({ username, password, role, display_name: displayName, email });
      onCreate();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-dark-800 border border-dark-500 rounded-lg p-6 w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-gray-200 mb-4">Create User</h2>

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Username *</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Password *</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
            >
              <option value="admin">Admin</option>
              <option value="operator">Operator</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>
        </div>

        {error && <div className="mt-3 text-xs text-red-400">{error}</div>}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-300 bg-dark-700 hover:bg-dark-600 rounded border border-dark-500">Cancel</button>
          <button onClick={handleCreate} className="px-4 py-2 text-sm text-white bg-accent-blue hover:bg-blue-500 rounded">Create User</button>
        </div>
      </div>
    </div>
  );
}
