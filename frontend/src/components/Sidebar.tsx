'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  UploadCloud,
  Map,
  ShieldCheck,
  DollarSign,
  Users,
  HardHat,
  LogOut,
  X,
  Layers,
} from 'lucide-react';
import type { UserRole } from './DashboardShell';

// ── Types ────────────────────────────────────────────────────────────────────

interface NavItem {
  label:     string;
  href:      string;
  icon:      React.ElementType;
}

// ── Role → nav items ──────────────────────────────────────────────────────

const NAV_BY_ROLE: Record<UserRole, NavItem[]> = {
  'Project Manager': [
    { label: 'Overall Dashboard',  href: '/',                icon: LayoutDashboard },
    { label: 'User Management',    href: '/user-management', icon: Users },
  ],
  'Site Engineer': [
    { label: 'Site Analysis',      href: '/',                  icon: Map },
    { label: 'Plan Upload',        href: '/upload',            icon: UploadCloud },
    { label: 'Clash Detection',    href: '/clash-detection',   icon: Layers },
  ],
  'Architect': [
    { label: 'Clash Detection',    href: '/clash-detection',   icon: Layers },
    { label: 'Plan Upload',        href: '/upload',            icon: UploadCloud },
  ],
  'Compliance Officer': [
    { label: 'Compliance Module', href: '/', icon: ShieldCheck },
  ],
  'Quantity Surveyor': [
    { label: 'Cost & Scheduling',  href: '/',                icon: DollarSign },
  ],
};

// ── Props ──────────────────────────────────────────────────────────────────────

interface SidebarProps {
  isOpen:    boolean;
  onClose:   () => void;
  role:      UserRole | null;
  onLogout:  () => void;
}

export default function Sidebar({
  isOpen,
  onClose,
  role,
  onLogout,
}: SidebarProps) {
  const pathname = usePathname();
  const navItems = role ? (NAV_BY_ROLE[role] ?? []) : [];

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 z-40 w-64 flex-col bg-industrial-surface border-r border-industrial-border">
        <SidebarContent
          pathname={pathname}
          navItems={navItems}
          onLogout={onLogout}
        />
      </aside>

      {/* Mobile sidebar (slide-in drawer) */}
      <aside
        className={`lg:hidden fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-industrial-surface border-r border-industrial-border transform transition-transform duration-200 ease-in-out ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded-md text-industrial-muted hover:text-industrial-text hover:bg-industrial-nav-hover transition-colors"
          aria-label="Close navigation"
        >
          <X className="h-5 w-5" />
        </button>
        <SidebarContent
          pathname={pathname}
          navItems={navItems}
          onLogout={onLogout}
          onNavClick={onClose}
        />
      </aside>
    </>
  );
}

// ── Inner content (shared by desktop + mobile) ─────────────────────────────────

function SidebarContent({
  pathname,
  navItems,
  onLogout,
  onNavClick,
}: {
  pathname:   string;
  navItems:   NavItem[];
  onLogout:   () => void;
  onNavClick?: () => void;
}) {
  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2.5 px-6 border-b border-industrial-border shrink-0">
        <HardHat className="h-6 w-6 text-industrial-accent" />
        <span className="text-lg font-bold tracking-tight text-industrial-text">
          Construction <span className="text-industrial-accent">AI</span>
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
        <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest text-industrial-muted">
          Main Menu
        </p>
        {navItems.map(({ label, href, icon: Icon }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={label}
              href={href}
              onClick={onNavClick}
              className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors border-l-2 ${
                isActive
                  ? 'border-industrial-accent bg-industrial-nav-active text-industrial-accent pl-2.5'
                  : 'border-transparent text-industrial-muted hover:bg-industrial-nav-hover hover:text-industrial-text'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer: logout + version */}
      <div className="px-3 py-4 border-t border-industrial-border shrink-0 space-y-2">
        <button
          onClick={onLogout}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-industrial-muted hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-500/10 dark:hover:text-rose-400 transition-colors border-l-2 border-transparent"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          Log Out
        </button>
        <p className="px-3 text-xs text-industrial-muted">
          Construction AI &bull; v0.1.0
        </p>
      </div>
    </div>
  );
}
