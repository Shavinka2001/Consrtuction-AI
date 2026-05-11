'use client';

import {
  LayoutDashboard,
  UploadCloud,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Map,
  ShieldCheck,
  DollarSign,
  Users,
  Construction,
} from 'lucide-react';
import { useUserRole, type UserRole } from '@/components/DashboardShell';
import ComplianceRoadmap from '@/components/ComplianceRoadmap';

// ── Shared stat cards data (Project Manager / generic) ─────────────────────────

const stats = [
  {
    label:    'Active Projects',
    value:    '12',
    icon:     LayoutDashboard,
    trend:    '+2 this month',
    positive: true,
  },
  {
    label:    'Plans Uploaded',
    value:    '348',
    icon:     UploadCloud,
    trend:    '+24 this week',
    positive: true,
  },
  {
    label:    'Open Clashes',
    value:    '57',
    icon:     AlertTriangle,
    trend:    '-8 resolved today',
    positive: false,
  },
  {
    label:    'Resolved Issues',
    value:    '291',
    icon:     CheckCircle2,
    trend:    'All time',
    positive: true,
  },
];

const recentActivity = [
  { id: 1, action: 'Plan uploaded',    detail: 'Level-3-MEP-v4.pdf — Block A',                      time: '5 min ago'  },
  { id: 2, action: 'Clash detected',   detail: 'Structural beam vs. HVAC duct — Grid D7',            time: '22 min ago' },
  { id: 3, action: 'Clash resolved',   detail: 'Pipe routing conflict — Level 2 East Wing',          time: '1 hr ago'   },
  { id: 4, action: 'Report generated', detail: 'Weekly clash summary exported (PDF)',                 time: '3 hr ago'   },
];

// ── Role panels ────────────────────────────────────────────────────────────────

function PlaceholderPanel({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed border-gray-200 dark:border-industrial-border bg-white dark:bg-industrial-surface py-24 text-center px-6 transition-colors duration-200">
      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-orange-50 dark:bg-industrial-accent-subtle">
        <Icon className="h-8 w-8 text-industrial-accent" />
      </span>
      <div>
        <p className="text-lg font-semibold text-gray-900 dark:text-industrial-text">{title}</p>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted max-w-sm">{description}</p>
      </div>
    </div>
  );
}

function ProjectManagerDashboard() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-industrial-text tracking-tight">
          Overall Dashboard
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
          Overview of all active construction projects and AI analysis activity.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {stats.map(({ label, value, icon: Icon, trend, positive }) => (
          <div
            key={label}
            className="rounded-lg bg-white shadow-sm border border-gray-100 dark:bg-industrial-surface dark:border-industrial-border dark:shadow-none p-5 flex flex-col gap-3 transition-colors duration-200"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-500 dark:text-industrial-muted">{label}</span>
              <span className="p-1.5 rounded-md bg-orange-50 dark:bg-industrial-accent-subtle">
                <Icon className="h-4 w-4 text-industrial-accent" />
              </span>
            </div>
            <p className="text-3xl font-bold text-gray-900 dark:text-industrial-text">{value}</p>
            <p className={`text-xs font-medium ${positive ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
              {trend}
            </p>
          </div>
        ))}
      </div>

      {/* User Management stub */}
      <div className="rounded-lg bg-white shadow-sm border border-gray-100 dark:bg-industrial-surface dark:border-industrial-border dark:shadow-none overflow-hidden transition-colors duration-200">
        <div className="px-5 py-4 border-b border-gray-100 dark:border-industrial-border flex items-center gap-2">
          <Users className="h-4 w-4 text-industrial-accent" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-industrial-text">User Management</h2>
        </div>
        <div className="px-5 py-8 text-center text-sm text-gray-400 dark:text-industrial-muted">
          User administration panel coming soon.
        </div>
      </div>

      {/* Recent activity */}
      <div className="rounded-lg bg-white shadow-sm border border-gray-100 dark:bg-industrial-surface dark:border-industrial-border dark:shadow-none overflow-hidden transition-colors duration-200">
        <div className="px-5 py-4 border-b border-gray-100 dark:border-industrial-border flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-industrial-text">Recent Activity</h2>
          <span className="text-xs text-gray-400 dark:text-industrial-muted">Today</span>
        </div>
        <ul className="divide-y divide-gray-100 dark:divide-industrial-border">
          {recentActivity.map((item) => (
            <li key={item.id} className="px-5 py-3.5 flex items-start gap-3">
              <Clock className="h-4 w-4 text-gray-400 dark:text-industrial-muted mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-industrial-text">{item.action}</p>
                <p className="text-xs text-gray-500 dark:text-industrial-muted truncate">{item.detail}</p>
              </div>
              <span className="text-xs text-gray-400 dark:text-industrial-muted whitespace-nowrap">{item.time}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// ── Role content map ───────────────────────────────────────────────────────────

const ROLE_CONTENT: Record<UserRole, React.ReactNode> = {
  'Project Manager': <ProjectManagerDashboard />,

  'Site Engineer': (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-industrial-text tracking-tight">
          Site Analysis &amp; Geospatial Module
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
          Upload site images for AI-powered analysis and geospatial clash detection.
        </p>
      </div>
      <PlaceholderPanel
        icon={Map}
        title="Image Upload &amp; AI Analysis"
        description="Upload construction site images here. The AI engine will detect safety hazards, equipment, and personnel."
      />
    </div>
  ),

  'Architect': (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-industrial-text tracking-tight">
          Architectural Plan Validation &amp; Clash Detection
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
          Upload and validate architectural drawings. Identify clashes across structural, MEP, and architectural layers.
        </p>
      </div>
      <PlaceholderPanel
        icon={Construction}
        title="Plan Clash Detection"
        description="Upload your CAD exports or blueprints to automatically detect intersecting elements across disciplines."
      />
    </div>
  ),

  'Compliance Officer': null,

  'Quantity Surveyor': (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-industrial-text tracking-tight">
          Intelligent Cost &amp; Scheduling Module
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
          AI-assisted cost estimation, Bill of Quantities generation, and schedule analysis.
        </p>
      </div>
      <PlaceholderPanel
        icon={DollarSign}
        title="Cost &amp; Schedule Analysis"
        description="Leverage AI to generate accurate BOQ estimates and optimise project timelines based on current site data."
      />
    </div>
  ),
};

// ── Page ───────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { role } = useUserRole();

  if (!role) return null;

  // Compliance Officer uses its own internal tab navigation
  if (role === 'Compliance Officer') {
    return <ComplianceRoadmap />;
  }

  return <>{ROLE_CONTENT[role]}</>;
}
