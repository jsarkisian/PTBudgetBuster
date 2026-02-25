import React, { useState } from 'react';
import { api, setToken } from '../utils/api';

export default function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [tempToken, setTempToken] = useState(null);
  const [tempUser, setTempUser] = useState(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changeLoading, setChangeLoading] = useState(false);
  const [changeError, setChangeError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await api.login(username, password);
      if (result.must_change_password) {
        setTempToken(result.token);
        setTempUser(result.user);
        setCurrentPassword(password);
        setMustChangePassword(true);
      } else {
        setToken(result.token);
        onLogin(result.user);
      }
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setChangeError('');

    if (newPassword.length < 14) {
      setChangeError('Password must be at least 14 characters');
      return;
    }
    if (!/[A-Z]/.test(newPassword)) {
      setChangeError('Password must contain an uppercase letter');
      return;
    }
    if (!/[a-z]/.test(newPassword)) {
      setChangeError('Password must contain a lowercase letter');
      return;
    }
    if (!/[0-9]/.test(newPassword)) {
      setChangeError('Password must contain a number');
      return;
    }
    if (!/[^A-Za-z0-9]/.test(newPassword)) {
      setChangeError('Password must contain a special character');
      return;
    }
    if (newPassword !== confirmPassword) {
      setChangeError('Passwords do not match');
      return;
    }
    if (newPassword === currentPassword) {
      setChangeError('New password must be different from current password');
      return;
    }

    setChangeLoading(true);
    try {
      setToken(tempToken);
      await api.changePassword(currentPassword, newPassword);
      onLogin(tempUser);
    } catch (err) {
      setToken(null);
      setChangeError(err.message || 'Failed to change password');
    } finally {
      setChangeLoading(false);
    }
  };

  if (mustChangePassword) {
    return (
      <div className="h-screen flex items-center justify-center bg-dark-950">
        <div className="w-full max-w-sm mx-4">
          <div className="text-center mb-8">
            <div className="text-5xl mb-3">🔒</div>
            <h1 className="text-2xl font-bold text-gray-100">Password Change Required</h1>
            <p className="text-sm text-gray-500 mt-1">You must set a new password before continuing</p>
          </div>

          <form onSubmit={handleChangePassword} className="bg-dark-800 border border-dark-600 rounded-lg p-6 space-y-4">
            {changeError && (
              <div className="bg-red-500/10 border border-red-500/30 rounded px-3 py-2 text-sm text-red-400">
                {changeError}
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
                placeholder="Enter new password"
                autoFocus
                required
                minLength={14}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Confirm New Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
                placeholder="Confirm new password"
                required
                minLength={14}
              />
            </div>

            <button
              type="submit"
              disabled={changeLoading}
              className="w-full py-2.5 bg-accent-blue hover:bg-blue-500 text-white rounded text-sm font-medium transition-colors disabled:opacity-50"
            >
              {changeLoading ? 'Changing password...' : 'Set New Password'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex items-center justify-center bg-dark-950">
      <div className="w-full max-w-sm mx-4">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🛡️</div>
          <h1 className="text-2xl font-bold text-gray-100">MCP-PT</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-dark-800 border border-dark-600 rounded-lg p-6 space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded px-3 py-2 text-sm text-red-400">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
              placeholder="admin"
              autoFocus
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 bg-dark-700 border border-dark-500 rounded text-sm text-gray-200 focus:border-accent-blue focus:outline-none"
              placeholder="••••••••"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-accent-blue hover:bg-blue-500 text-white rounded text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
