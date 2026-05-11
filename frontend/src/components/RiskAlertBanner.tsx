'use client';

/**
 * RiskAlertBanner
 * ───────────────
 * Reusable alert component for proactive risk warnings from the backend
 * risk-mitigation module.
 *
 * Backend binding
 * ───────────────
 * Shape of one alert maps to DetectedDeviation in app/models/risk.py:
 *
 *   {
 *     id              : string            (deviation_id from backend)
 *     severity        : 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
 *     title           : string            (permit_type + short label)
 *     message         : string            (description)
 *     penaltyLkr      : number | null     (FinancialPenalty.estimated_penalty_usd
 *                                          converted to LKR — do conversion in caller)
 *     dailyAccrualLkr : number | null     (daily_accrual_usd converted)
 *     stopWork        : boolean           (LegalWarning.stop_work_required)
 *     statute         : string | null     (LegalWarning.statute_reference)
 *     correctiveAction: string | null     (LegalWarning.corrective_action)
 *   }
 *
 * Usage
 * ─────
 * // Static (dev / demo)
 * <RiskAlertBanner alerts={MOCK_ALERTS} />
 *
 * // Wired to backend
 * const { data } = useSWR(`/api/v1/compliance/analyze-risk`, fetcher);
 * const alerts   = mapDeviationsToAlerts(data?.deviations ?? []);
 * <RiskAlertBanner alerts={alerts} loading={!data} />
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  TriangleAlert,
  OctagonX,
  AlertCircle,
  Info,
  ChevronDown,
  X,
  Siren,
  Ban,
  Scale,
  RefreshCcw,
  Loader2,
} from 'lucide-react';

// ── Public types ──────────────────────────────────────────────────────────────

export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface RiskAlert {
  /** Unique id (use deviation_id from backend, or generate client-side for demo) */
  id: string;
  severity: AlertSeverity;
  /** Short headline, e.g. "Foundation Work Without UDA Approval" */
  title: string;
  /** Detailed description of the violation */
  message: string;
  /** Estimated one-time penalty in LKR (null when not calculable) */
  penaltyLkr?: number | null;
  /** Daily accrual penalty in LKR (null when not applicable) */
  dailyAccrualLkr?: number | null;
  /** Whether a stop-work order is mandated */
  stopWork?: boolean;
  /** Statute reference string, e.g. "UDA Law No. 41 of 1978, Section 14" */
  statute?: string | null;
  /** What the project team must do to resolve (from LegalWarning.corrective_action) */
  correctiveAction?: string | null;
}

export interface RiskAlertBannerProps {
  alerts: RiskAlert[];
  /** If true, shows a loading skeleton instead of alerts */
  loading?: boolean;
  /** If provided, shown above the alert list */
  projectName?: string;
  /** Called when user dismisses a single alert (client-side only; does not call API) */
  onDismiss?: (id: string) => void;
  /** Optional wrapper className */
  className?: string;
}

// ── Severity config ───────────────────────────────────────────────────────────

interface SeverityConfig {
  icon:        React.ElementType;
  bannerBg:    string;
  border:      string;
  iconCls:     string;
  titleCls:    string;
  badge:       string;
  badgeLabel:  string;
  expandBg:    string;
}

const SEVERITY: Record<AlertSeverity, SeverityConfig> = {
  LOW: {
    icon:        Info,
    bannerBg:    'bg-blue-500/8',
    border:      'border-blue-500/30',
    iconCls:     'text-blue-400',
    titleCls:    'text-blue-300',
    badge:       'bg-blue-500/15 text-blue-400 border-blue-500/25',
    badgeLabel:  'Low',
    expandBg:    'bg-blue-500/5',
  },
  MEDIUM: {
    icon:        TriangleAlert,
    bannerBg:    'bg-amber-500/8',
    border:      'border-amber-500/35',
    iconCls:     'text-amber-400',
    titleCls:    'text-amber-300',
    badge:       'bg-amber-500/15 text-amber-400 border-amber-500/25',
    badgeLabel:  'Medium',
    expandBg:    'bg-amber-500/5',
  },
  HIGH: {
    icon:        AlertCircle,
    bannerBg:    'bg-red-500/8',
    border:      'border-red-500/35',
    iconCls:     'text-red-400',
    titleCls:    'text-red-300',
    badge:       'bg-red-500/15 text-red-400 border-red-500/25',
    badgeLabel:  'High',
    expandBg:    'bg-red-500/5',
  },
  CRITICAL: {
    icon:        OctagonX,
    bannerBg:    'bg-red-900/25',
    border:      'border-red-500/60',
    iconCls:     'text-red-400',
    titleCls:    'text-red-300',
    badge:       'bg-red-500/25 text-red-300 border-red-500/40',
    badgeLabel:  'Critical',
    expandBg:    'bg-red-900/20',
  },
};

const SORT_ORDER: Record<AlertSeverity, number> = {
  CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3,
};

// ── Formatters ────────────────────────────────────────────────────────────────

function formatLKR(amount: number) {
  return `LKR ${amount.toLocaleString('en-LK')}`;
}

// ── Framer Motion variants ─────────────────────────────────────────────────────

const listVariant = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.07 } },
};

const itemVariant = {
  hidden: { opacity: 0, y: 12, scale: 0.98 },
  show:   { opacity: 1, y: 0,  scale: 1, transition: { duration: 0.3, ease: 'easeOut' as const } },
  exit:   { opacity: 0, x: 40, scale: 0.96, transition: { duration: 0.22, ease: 'easeIn' as const } },
};

const expandVariant = {
  hidden: { height: 0, opacity: 0 },
  show:   { height: 'auto', opacity: 1, transition: { duration: 0.25, ease: 'easeOut' as const } },
  exit:   { height: 0, opacity: 0, transition: { duration: 0.18, ease: 'easeIn' as const } },
};

// ── Single alert card ─────────────────────────────────────────────────────────

function AlertCard({
  alert,
  onDismiss,
}: {
  alert: RiskAlert;
  onDismiss?: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const cfg = SEVERITY[alert.severity];
  const Icon = cfg.icon;

  const hasDetails =
    alert.penaltyLkr != null ||
    alert.dailyAccrualLkr != null ||
    alert.statute ||
    alert.correctiveAction;

  return (
    <motion.div
      layout
      variants={itemVariant}
      className={`rounded-xl border ${cfg.border} ${cfg.bannerBg} overflow-hidden`}
    >
      {/* ── Header row ────────────────────────────────────────────────────────── */}
      <div className="flex items-start gap-3 px-4 py-3.5">
        {/* Severity icon */}
        <span className="mt-0.5 shrink-0">
          <Icon className={`h-4.5 w-4.5 ${cfg.iconCls}`} style={{ width: '1.125rem', height: '1.125rem' }} />
        </span>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-0.5">
            {/* Severity badge */}
            <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${cfg.badge}`}>
              {cfg.badgeLabel} Risk
            </span>

            {/* Stop-work badge */}
            {alert.stopWork && (
              <span className="inline-flex items-center gap-1 rounded-full border border-red-500/50 bg-red-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-300">
                <Ban className="h-2.5 w-2.5" />
                Stop-Work Order
              </span>
            )}
          </div>

          {/* Title */}
          <p className={`text-sm font-semibold leading-tight ${cfg.titleCls}`}>{alert.title}</p>

          {/* Message */}
          <p className="mt-1 text-xs text-industrial-muted leading-relaxed">{alert.message}</p>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0 ml-1">
          {hasDetails && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              aria-label="Toggle details"
              className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-industrial-surface-2 transition-colors"
            >
              <motion.div
                animate={{ rotate: expanded ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <ChevronDown className="h-4 w-4 text-industrial-muted" />
              </motion.div>
            </button>
          )}
          {onDismiss && (
            <button
              type="button"
              onClick={() => onDismiss(alert.id)}
              aria-label="Dismiss alert"
              className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-industrial-surface-2 transition-colors"
            >
              <X className="h-3.5 w-3.5 text-industrial-muted hover:text-industrial-text" />
            </button>
          )}
        </div>
      </div>

      {/* ── Expanded detail ────────────────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="detail"
            variants={expandVariant}
            initial="hidden"
            animate="show"
            exit="exit"
            className="overflow-hidden"
          >
            <div className={`border-t ${cfg.border} ${cfg.expandBg} px-4 py-4 grid grid-cols-1 sm:grid-cols-2 gap-4`}>
              {/* Financial penalty */}
              {(alert.penaltyLkr != null || alert.dailyAccrualLkr != null) && (
                <div className="flex flex-col gap-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-industrial-muted">
                    Financial Exposure
                  </p>
                  {alert.penaltyLkr != null && (
                    <div className="flex items-center gap-2">
                      <Scale className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                      <span className="text-xs text-industrial-text">
                        One-time penalty:{' '}
                        <span className="font-bold text-amber-300">{formatLKR(alert.penaltyLkr)}</span>
                      </span>
                    </div>
                  )}
                  {alert.dailyAccrualLkr != null && (
                    <div className="flex items-center gap-2">
                      <RefreshCcw className="h-3.5 w-3.5 text-red-400 shrink-0" />
                      <span className="text-xs text-industrial-text">
                        Daily accrual:{' '}
                        <span className="font-bold text-red-300">{formatLKR(alert.dailyAccrualLkr)}/day</span>
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Statute */}
              {alert.statute && (
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-industrial-muted mb-1.5">
                    Legal Statute
                  </p>
                  <p className="text-xs text-industrial-text font-mono bg-industrial-bg/60 rounded-md px-3 py-2 border border-industrial-border leading-relaxed">
                    {alert.statute}
                  </p>
                </div>
              )}

              {/* Corrective action */}
              {alert.correctiveAction && (
                <div className="sm:col-span-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-industrial-muted mb-1.5">
                    Required Corrective Action
                  </p>
                  <div className="flex items-start gap-2 rounded-lg bg-industrial-surface border border-industrial-border px-3 py-2.5">
                    <Siren className={`h-4 w-4 ${cfg.iconCls} shrink-0 mt-0.5`} />
                    <p className="text-xs text-industrial-text leading-relaxed">{alert.correctiveAction}</p>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function AlertSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-industrial-border bg-industrial-surface px-4 py-4 animate-pulse"
        >
          <div className="flex items-start gap-3">
            <div className="h-5 w-5 rounded-full bg-industrial-surface-2 mt-0.5 shrink-0" />
            <div className="flex-1 space-y-2">
              <div className="h-3 w-24 rounded bg-industrial-surface-2" />
              <div className="h-3.5 w-56 rounded bg-industrial-surface-2" />
              <div className="h-3 w-full rounded bg-industrial-surface-2" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function RiskAlertBanner({
  alerts: initialAlerts,
  loading = false,
  projectName,
  onDismiss,
  className = '',
}: RiskAlertBannerProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  function handleDismiss(id: string) {
    setDismissed((prev) => new Set([...prev, id]));
    onDismiss?.(id);
  }

  const visible = [...initialAlerts]
    .filter((a) => !dismissed.has(a.id))
    .sort((a, b) => SORT_ORDER[a.severity] - SORT_ORDER[b.severity]);

  const criticalCount  = visible.filter((a) => a.severity === 'CRITICAL').length;
  const highCount      = visible.filter((a) => a.severity === 'HIGH').length;
  const stopWorkCount  = visible.filter((a) => a.stopWork).length;
  const hasStopWork    = stopWorkCount > 0;

  return (
    <div className={`space-y-4 ${className}`}>
      {/* ── Section header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-500/10 border border-red-500/20">
            <TriangleAlert className="h-4 w-4 text-red-400" />
          </span>
          <div>
            <h2 className="text-sm font-bold text-industrial-text">
              Proactive Risk Warnings
            </h2>
            {projectName && (
              <p className="text-[10px] text-industrial-muted">{projectName}</p>
            )}
          </div>
        </div>

        {/* Summary pills */}
        {!loading && visible.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {criticalCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-red-500/40 bg-red-500/15 px-2.5 py-0.5 text-[11px] font-bold text-red-300">
                <OctagonX className="h-3 w-3" />
                {criticalCount} Critical
              </span>
            )}
            {highCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-red-400/30 bg-red-400/10 px-2.5 py-0.5 text-[11px] font-bold text-red-400">
                <AlertCircle className="h-3 w-3" />
                {highCount} High
              </span>
            )}
            {hasStopWork && (
              <span className="inline-flex items-center gap-1 rounded-full border border-red-500/50 bg-red-500/20 px-2.5 py-0.5 text-[11px] font-bold text-red-300">
                <Ban className="h-3 w-3" />
                {stopWorkCount} Stop-Work
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Critical stop-work header strip ────────────────────────────────────── */}
      <AnimatePresence>
        {hasStopWork && !loading && (
          <motion.div
            key="stop-work-strip"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.3 } }}
            exit={{ opacity: 0, y: -8, transition: { duration: 0.2 } }}
            className="flex items-center gap-3 rounded-xl border border-red-500/50 bg-red-500/12 px-4 py-3"
          >
            <Ban className="h-5 w-5 text-red-400 shrink-0 animate-pulse" />
            <p className="text-sm font-bold text-red-300">
              Stop-Work Order Active — Site activity must cease until deviations are resolved and approvals are reinstated.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Loading state ─────────────────────────────────────────────────────── */}
      {loading && (
        <div className="flex items-center gap-2 text-xs text-industrial-muted mb-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Analysing compliance deviations...
        </div>
      )}
      {loading && <AlertSkeleton />}

      {/* ── Empty state ────────────────────────────────────────────────────────── */}
      {!loading && visible.length === 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/6 px-4 py-4"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 shrink-0">
            <TriangleAlert className="h-4 w-4 text-emerald-400" />
          </span>
          <div>
            <p className="text-sm font-semibold text-emerald-400">No Active Risk Warnings</p>
            <p className="text-xs text-industrial-muted mt-0.5">
              All compliance deviations have been resolved or no analysis has been run yet.
            </p>
          </div>
        </motion.div>
      )}

      {/* ── Alert list ────────────────────────────────────────────────────────── */}
      {!loading && (
        <motion.div
          className="space-y-3"
          variants={listVariant}
          initial="hidden"
          animate="show"
        >
          <AnimatePresence mode="popLayout">
            {visible.map((alert) => (
              <AlertCard
                key={alert.id}
                alert={alert}
                onDismiss={onDismiss ? handleDismiss : undefined}
              />
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  );
}
