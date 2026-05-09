'use client';

import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import { Bell, UserCircle2, Menu, Sun, Moon } from 'lucide-react';

interface TopNavProps {
  onMenuClick: () => void;
}

export default function TopNav({ onMenuClick }: TopNavProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Avoid hydration mismatch — only render theme-dependent UI on client
  useEffect(() => setMounted(true), []);

  return (
    <header className="fixed top-0 right-0 left-0 lg:left-64 z-30 flex h-16 items-center justify-between border-b bg-white border-gray-200 dark:bg-industrial-surface dark:border-industrial-border px-4 lg:px-6 transition-colors duration-200">
      {/* Left: hamburger on mobile, breadcrumb on desktop */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-industrial-muted dark:hover:bg-industrial-nav-hover dark:hover:text-industrial-text transition-colors"
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="hidden lg:block text-sm font-medium text-gray-500 dark:text-industrial-muted">
          Construction AI Platform
        </span>
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-1">
        {/* Theme toggle */}
        {mounted && (
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="p-2 rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-industrial-muted dark:hover:bg-industrial-nav-hover dark:hover:text-industrial-text transition-colors"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? (
              <Sun className="h-5 w-5" />
            ) : (
              <Moon className="h-5 w-5" />
            )}
          </button>
        )}

        {/* Notification bell */}
        <button
          className="relative p-2 rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-industrial-muted dark:hover:bg-industrial-nav-hover dark:hover:text-industrial-text transition-colors"
          aria-label="Notifications"
        >
          <Bell className="h-5 w-5" />
          <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-industrial-accent ring-2 ring-white dark:ring-industrial-surface" />
        </button>

        {/* Divider */}
        <div className="mx-1 h-6 w-px bg-gray-200 dark:bg-industrial-border" />

        {/* User profile */}
        <button
          className="flex items-center gap-2 rounded-md px-2 py-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-industrial-muted dark:hover:bg-industrial-nav-hover dark:hover:text-industrial-text transition-colors"
          aria-label="User profile"
        >
          <UserCircle2 className="h-7 w-7" />
          <span className="hidden sm:block text-sm font-medium text-gray-900 dark:text-industrial-text">
            Site Manager
          </span>
        </button>
      </div>
    </header>
  );
}
