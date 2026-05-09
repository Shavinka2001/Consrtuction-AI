'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import Image from 'next/image';
import api from '@/lib/api';

export default function RegisterPage() {
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');

    if (!username.trim()) {
      setError('Username is required.');
      return;
    }

    if (password.length < 3) {
      setError('Password must be at least 3 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);

    try {
      await api.post('http://127.0.0.1:8000/api/register', {
        username: username.trim(),
        email: email.trim(),
        password,
        role: 'Project Manager',
      });

      setSuccess(true);
      // Brief pause so the success message is visible before redirecting.
      setTimeout(() => router.push('/login'), 1500);
    } catch (err: unknown) {
      // FastAPI returns errors as { detail: string }
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : 'Registration failed. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4 py-12">
        <div className="max-w-md w-full mx-auto p-8 bg-white rounded-2xl shadow-lg border border-slate-100">
          <div className="w-20 h-20 mx-auto mb-4">
            <Image
              src="/logo.png"
              alt="Construction AI"
              width={80}
              height={80}
              className="w-full h-full object-contain"
              priority
            />
          </div>
          <div className="flex flex-col items-center gap-3 py-4 text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-500" />
            <p className="text-gray-900 font-semibold text-lg">
              Account created!
            </p>
            <p className="text-gray-500 text-sm">
              Redirecting you to login…
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4 py-12">
      <div className="max-w-md w-full mx-auto p-8 bg-white rounded-2xl shadow-lg border border-slate-100">

        {/* Logo */}
        <div className="w-20 h-20 mx-auto mb-4">
          <Image
            src="/logo.png"
            alt="Construction AI"
            width={80}
            height={80}
            className="w-full h-full object-contain"
            priority
          />
        </div>

        <h1 className="text-2xl font-bold text-gray-900 mb-1 text-center">
          Create an account
        </h1>
        <p className="text-gray-500 text-sm text-center mb-7">
          Join Construction AI and streamline your projects
        </p>

        {error && (
          <div className="flex items-start gap-2.5 bg-rose-50 border border-rose-200 text-rose-600 text-sm rounded-lg px-4 py-3 mb-6">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Username */}
          <div>
            <label
              htmlFor="username"
              className="block text-sm font-medium text-gray-700 mb-1.5"
            >
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. site_eng"
              className="w-full bg-white border border-gray-300 rounded-lg px-3.5 py-2.5 text-gray-900 placeholder-gray-400 text-sm focus:outline-none focus:ring-2 focus:ring-industrial-accent focus:border-transparent transition"
            />
          </div>

          {/* Email */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700 mb-1.5"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="e.g. you@company.com"
              className="w-full bg-white border border-gray-300 rounded-lg px-3.5 py-2.5 text-gray-900 placeholder-gray-400 text-sm focus:outline-none focus:ring-2 focus:ring-industrial-accent focus:border-transparent transition"
            />
          </div>

          {/* Password */}
          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 mb-1.5"
            >
              Password
              <span className="ml-1.5 text-gray-400 font-normal">(min. 8 characters)</span>
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full bg-white border border-gray-300 rounded-lg px-3.5 py-2.5 text-gray-900 placeholder-gray-400 text-sm focus:outline-none focus:ring-2 focus:ring-industrial-accent focus:border-transparent transition"
            />
          </div>

          {/* Confirm Password */}
          <div>
            <label
              htmlFor="confirmPassword"
              className="block text-sm font-medium text-gray-700 mb-1.5"
            >
              Confirm Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full bg-white border border-gray-300 rounded-lg px-3.5 py-2.5 text-gray-900 placeholder-gray-400 text-sm focus:outline-none focus:ring-2 focus:ring-industrial-accent focus:border-transparent transition"
            />
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-industrial-accent hover:bg-industrial-accent-hover disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold rounded-lg px-4 py-2.5 text-sm transition-colors mt-1"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            {loading ? 'Creating account…' : 'Create Account'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-gray-500">
          Already have an account?{' '}
          <Link
            href="/login"
            className="text-industrial-accent hover:text-industrial-accent-hover font-medium transition-colors"
          >
            Log in
          </Link>
      </p>
      </div>
    </div>
  );
}
