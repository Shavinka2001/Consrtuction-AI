'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Loader2, AlertCircle } from 'lucide-react';
import Image from 'next/image';
import api, { setApiToken } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const { data } = await api.post<{
        access_token: string;
        role: string;
        username: string;
      }>('http://127.0.0.1:8000/api/login', { email, password });

      // Persist token and role so DashboardShell can read them.
      setApiToken(data.access_token);
      localStorage.setItem('constructai_role',     data.role);
      localStorage.setItem('constructai_username', data.username);

      router.replace('/');
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : 'Invalid email or password. Please try again.',
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="max-w-md w-full mx-auto p-8 bg-white rounded-2xl shadow-xl">
        {/* Logo */}
        <div className="w-24 h-24 mx-auto mb-6">
          <Image
            src="/logo.png"
            alt="Construction AI"
            width={96}
            height={96}
            className="w-full h-full object-contain"
            priority
          />
        </div>

        <h1 className="text-2xl font-bold text-gray-900 mb-1 text-center">
          Welcome back
        </h1>
        <p className="text-gray-500 text-sm text-center mb-7">
          Sign in to your Construction AI account
        </p>

        {error && (
          <div className="flex items-start gap-2.5 bg-rose-50 border border-rose-200 text-rose-600 text-sm rounded-lg px-4 py-3 mb-6">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
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
              placeholder="name@company.com"
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
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-gray-500">
          Don&apos;t have an account?{' '}
          <Link
            href="/register"
            className="text-industrial-accent hover:text-industrial-accent-hover font-medium transition-colors"
          >
            Sign up
          </Link>
        </p>

      </div>
    </div>
  );
}

