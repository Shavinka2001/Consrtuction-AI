'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from './Sidebar';
import TopNav from './TopNav';
import { clearApiToken, getApiToken } from '@/lib/api';

// ── Role context ───────────────────────────────────────────────────────────────

export type UserRole =
  | 'Project Manager'
  | 'Site Engineer'
  | 'Architect'
  | 'Compliance Officer'
  | 'Quantity Surveyor';

interface RoleContextValue {
  role: UserRole | null;
  username: string | null;
}

const RoleContext = createContext<RoleContextValue>({ role: null, username: null });

/** Consume the authenticated user's role anywhere inside the dashboard. */
export function useUserRole(): RoleContextValue {
  return useContext(RoleContext);
}

// ── Shell ──────────────────────────────────────────────────────────────────────

interface DashboardShellProps {
  children: React.ReactNode;
}

export default function DashboardShell({ children }: DashboardShellProps) {
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [role, setRole] = useState<UserRole | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  // `ready` stays false until the client-side localStorage check completes,
  // preventing any hydration mismatch between server and first client render.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token    = getApiToken();
    const storedRole     = localStorage.getItem('constructai_role') as UserRole | null;
    const storedUsername = localStorage.getItem('constructai_username');

    if (!token || !storedRole) {
      router.replace('/login');
      return;
    }

    setRole(storedRole);
    setUsername(storedUsername);
    setReady(true);
  }, [router]);

  const handleLogout = () => {
    clearApiToken();
    localStorage.removeItem('constructai_role');
    localStorage.removeItem('constructai_username');
    router.replace('/login');
  };

  // Render nothing (no flash of protected content) while auth check runs.
  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-industrial-bg">
        <span className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-industrial-accent" />
      </div>
    );
  }

  return (
    <RoleContext.Provider value={{ role, username }}>
      <div className="min-h-screen bg-gray-50 dark:bg-industrial-bg transition-colors duration-200">
        {/* Sidebar */}
        <Sidebar
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          role={role}
          username={username}
          onLogout={handleLogout}
        />

        {/* Mobile overlay */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/60 lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Main area: offset by sidebar width on lg+ */}
        <div className="flex flex-col lg:pl-64 min-h-screen">
          <TopNav onMenuClick={() => setSidebarOpen(true)} />

          {/* Content: push below the fixed TopNav */}
          <main className="flex-1 overflow-y-auto pt-16">
            <div className="px-4 lg:px-6 py-6">{children}</div>
          </main>
        </div>
      </div>
    </RoleContext.Provider>
  );
}
