'use client';

import { useState } from 'react';
import {
  UserPlus,
  Trash2,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ShieldCheck,
  HardHat,
  Ruler,
  BarChart3,
} from 'lucide-react';
import api from '@/lib/api';

// ── Types ──────────────────────────────────────────────────────────────────────

type SubRole = 'Site Engineer' | 'Architect' | 'Compliance Officer' | 'Quantity Surveyor';

interface TeamUser {
  id:       string;
  username: string;
  email:    string;
  role:     SubRole;
  status:   'Active';
}

// ── Constants ──────────────────────────────────────────────────────────────────

const SUB_ROLES: SubRole[] = [
  'Site Engineer',
  'Architect',
  'Compliance Officer',
  'Quantity Surveyor',
];

const INITIAL_USERS: TeamUser[] = [
  { id: '1', username: 'alex_eng',    email: 'alex@constructai.io',    role: 'Site Engineer',      status: 'Active' },
  { id: '2', username: 'sara_arch',   email: 'sara@constructai.io',    role: 'Architect',          status: 'Active' },
  { id: '3', username: 'tom_comply',  email: 'tom@constructai.io',     role: 'Compliance Officer', status: 'Active' },
];

// ── Role badge config ──────────────────────────────────────────────────────────

const ROLE_BADGE: Record<SubRole, { bg: string; text: string; icon: React.ElementType }> = {
  'Site Engineer':      { bg: 'bg-blue-50 dark:bg-blue-500/10',    text: 'text-blue-700 dark:text-blue-400',    icon: HardHat    },
  'Architect':          { bg: 'bg-violet-50 dark:bg-violet-500/10', text: 'text-violet-700 dark:text-violet-400', icon: Ruler      },
  'Compliance Officer': { bg: 'bg-emerald-50 dark:bg-emerald-500/10', text: 'text-emerald-700 dark:text-emerald-400', icon: ShieldCheck },
  'Quantity Surveyor':  { bg: 'bg-amber-50 dark:bg-amber-500/10',   text: 'text-amber-700 dark:text-amber-400',   icon: BarChart3  },
};

// ── Shared input class ─────────────────────────────────────────────────────────

const inputCls =
  'w-full bg-white dark:bg-industrial-surface border border-gray-300 dark:border-industrial-border rounded-lg px-3.5 py-2.5 text-gray-900 dark:text-industrial-text placeholder-gray-400 dark:placeholder-industrial-muted text-sm focus:outline-none focus:ring-2 focus:ring-industrial-accent focus:border-transparent transition';

// ── Page ───────────────────────────────────────────────────────────────────────

export default function UserManagementPage() {
  const [users, setUsers] = useState<TeamUser[]>(INITIAL_USERS);

  // form state
  const [username, setUsername] = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [role,     setRole]     = useState<SubRole>('Site Engineer');

  const [formError,   setFormError]   = useState('');
  const [formSuccess, setFormSuccess] = useState('');
  const [loading,     setLoading]     = useState(false);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError('');
    setFormSuccess('');

    if (!username.trim() || !email.trim() || !password) {
      setFormError('All fields are required.');
      return;
    }

    setLoading(true);
    try {
      await api.post('http://127.0.0.1:8000/api/register', {
        username: username.trim(),
        email:    email.trim(),
        password,
        role,
      });

      setUsers((prev) => [
        ...prev,
        {
          id:       String(Date.now()),
          username: username.trim(),
          email:    email.trim(),
          role,
          status:   'Active',
        },
      ]);

      setFormSuccess(`${role} "${username.trim()}" created successfully.`);
      setUsername('');
      setEmail('');
      setPassword('');
      setRole('Site Engineer');
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setFormError(
        typeof detail === 'string' ? detail : 'Failed to create user. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  }

  function handleDelete(id: string) {
    setUsers((prev) => prev.filter((u) => u.id !== id));
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto">

      {/* ── Page header ── */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-industrial-text">
          User Management
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
          Add and manage your construction project team members.
        </p>
      </div>

      {/* ── Add User form card ── */}
      <div className="rounded-xl border border-gray-100 dark:border-industrial-border bg-white dark:bg-industrial-surface shadow-sm dark:shadow-none transition-colors duration-200">
        <div className="border-b border-gray-100 dark:border-industrial-border px-6 py-4">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-industrial-text flex items-center gap-2">
            <UserPlus className="h-4 w-4 text-industrial-accent" />
            Add New Team Member
          </h2>
          <p className="mt-0.5 text-xs text-gray-400 dark:text-industrial-muted">
            New members will be assigned the selected role immediately.
          </p>
        </div>

        <form onSubmit={handleCreate} className="p-6">
          {/* Alerts */}
          {formError && (
            <div className="mb-5 flex items-start gap-2.5 rounded-lg border border-rose-200 bg-rose-50 dark:border-rose-500/30 dark:bg-rose-500/10 px-4 py-3 text-sm text-rose-600 dark:text-rose-400">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{formError}</span>
            </div>
          )}
          {formSuccess && (
            <div className="mb-5 flex items-start gap-2.5 rounded-lg border border-emerald-200 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-400">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{formSuccess}</span>
            </div>
          )}

          {/* Grid fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Username */}
            <div>
              <label htmlFor="um-username" className="block text-sm font-medium text-gray-700 dark:text-industrial-text mb-1.5">
                Username
              </label>
              <input
                id="um-username"
                type="text"
                autoComplete="off"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. john_eng"
                className={inputCls}
              />
            </div>

            {/* Email */}
            <div>
              <label htmlFor="um-email" className="block text-sm font-medium text-gray-700 dark:text-industrial-text mb-1.5">
                Email
              </label>
              <input
                id="um-email"
                type="email"
                autoComplete="off"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. john@co.com"
                className={inputCls}
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="um-password" className="block text-sm font-medium text-gray-700 dark:text-industrial-text mb-1.5">
                Password
              </label>
              <input
                id="um-password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className={inputCls}
              />
            </div>

            {/* Role */}
            <div>
              <label htmlFor="um-role" className="block text-sm font-medium text-gray-700 dark:text-industrial-text mb-1.5">
                Role
              </label>
              <select
                id="um-role"
                required
                value={role}
                onChange={(e) => setRole(e.target.value as SubRole)}
                className={`${inputCls} appearance-none cursor-pointer`}
              >
                {SUB_ROLES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Submit */}
          <div className="mt-5 flex justify-end">
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-2 bg-industrial-accent hover:bg-industrial-accent-hover disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold rounded-lg px-5 py-2.5 text-sm transition-colors"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <UserPlus className="h-4 w-4" />
              )}
              {loading ? 'Creating…' : 'Create User'}
            </button>
          </div>
        </form>
      </div>

      {/* ── User list table ── */}
      <div className="rounded-xl border border-gray-100 dark:border-industrial-border bg-white dark:bg-industrial-surface shadow-sm dark:shadow-none transition-colors duration-200 overflow-hidden">
        <div className="border-b border-gray-100 dark:border-industrial-border px-6 py-4">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-industrial-text">
            Team Members
          </h2>
          <p className="mt-0.5 text-xs text-gray-400 dark:text-industrial-muted">
            {users.length} member{users.length !== 1 ? 's' : ''} in your project
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-industrial-border bg-gray-50 dark:bg-industrial-surface-2">
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 dark:text-industrial-muted uppercase tracking-wider">
                  User
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 dark:text-industrial-muted uppercase tracking-wider">
                  Email
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 dark:text-industrial-muted uppercase tracking-wider">
                  Role
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 dark:text-industrial-muted uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 dark:text-industrial-muted uppercase tracking-wider">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-industrial-border">
              {users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-sm text-gray-400 dark:text-industrial-muted">
                    No team members yet. Add your first member above.
                  </td>
                </tr>
              ) : (
                users.map((user) => {
                  const badge = ROLE_BADGE[user.role];
                  const BadgeIcon = badge.icon;
                  return (
                    <tr
                      key={user.id}
                      className="hover:bg-gray-50 dark:hover:bg-industrial-nav-hover transition-colors duration-100"
                    >
                      {/* User */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-industrial-accent/10 dark:bg-industrial-accent-subtle">
                            <span className="text-xs font-bold text-industrial-accent uppercase">
                              {user.username.charAt(0)}
                            </span>
                          </div>
                          <span className="font-medium text-gray-900 dark:text-industrial-text">
                            {user.username}
                          </span>
                        </div>
                      </td>

                      {/* Email */}
                      <td className="px-6 py-4 text-gray-500 dark:text-industrial-muted">
                        {user.email}
                      </td>

                      {/* Role badge */}
                      <td className="px-6 py-4">
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${badge.bg} ${badge.text}`}>
                          <BadgeIcon className="h-3 w-3" />
                          {user.role}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Active
                        </span>
                      </td>

                      {/* Delete */}
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleDelete(user.id)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-industrial-border px-3 py-1.5 text-xs font-medium text-gray-500 dark:text-industrial-muted hover:border-rose-300 hover:bg-rose-50 hover:text-rose-600 dark:hover:border-rose-500/40 dark:hover:bg-rose-500/10 dark:hover:text-rose-400 transition-colors"
                          aria-label={`Delete ${user.username}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
