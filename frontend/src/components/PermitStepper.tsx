'use client';

/**
 * PermitStepper
 * ─────────────
 * Displays the permit workflow as an animated horizontal (desktop) /
 * vertical (mobile) stepper.
 *
 * Backend binding
 * ───────────────
 * The component is purely presentational. Pass in `currentStatus` from the
 * API response (GET /api/v1/compliance/{project_id}/status) and optionally
 * a `rejectionNote` when the status is REJECTED.
 *
 * WorkflowStatus enum mirrors app/models/compliance.py:
 *   NOT_STARTED | DOCUMENT_GATHERING | SUBMITTED | UNDER_REVIEW | APPROVED | REJECTED
 */

import { motion, AnimatePresence } from 'framer-motion';
import {
  FolderOpen,
  Upload,
  Search,
  BadgeCheck,
  XCircle,
  Circle,
  ChevronRight,
  AlertCircle,
} from 'lucide-react';

// ── Public types (re-export so parent can import from one place) ───────────────

export type WorkflowStatus =
  | 'NOT_STARTED'
  | 'DOCUMENT_GATHERING'
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'REJECTED';

export interface PermitStepperProps {
  /** The permit's current backend status */
  currentStatus: WorkflowStatus;
  /** Human-readable label for this permit (e.g. "UDA Development Permission") */
  permitName?: string;
  /** Authority handling this permit (e.g. "Urban Development Authority") */
  authority?: string;
  /** Optional note shown when status === REJECTED */
  rejectionNote?: string;
  /** If true, the stepper uses a compact vertical layout regardless of viewport */
  forceVertical?: boolean;
  /** Optional className forwarded to the wrapper */
  className?: string;
}

// ── Step definitions ──────────────────────────────────────────────────────────

interface StepDef {
  id: WorkflowStatus;
  label: string;
  sublabel: string;
  icon: React.ElementType;
}

const STEPS: StepDef[] = [
  {
    id:       'NOT_STARTED',
    label:    'Not Started',
    sublabel: 'Awaiting initiation',
    icon:     Circle,
  },
  {
    id:       'DOCUMENT_GATHERING',
    label:    'Gathering Docs',
    sublabel: 'Compiling required documents',
    icon:     FolderOpen,
  },
  {
    id:       'SUBMITTED',
    label:    'Submitted',
    sublabel: 'Application lodged with authority',
    icon:     Upload,
  },
  {
    id:       'UNDER_REVIEW',
    label:    'Under Review',
    sublabel: 'Authority reviewing application',
    icon:     Search,
  },
  {
    id:       'APPROVED',
    label:    'Approved',
    sublabel: 'Permit granted',
    icon:     BadgeCheck,
  },
];

// Numeric rank for progress comparison (REJECTED sits outside the happy path)
const STATUS_RANK: Record<WorkflowStatus, number> = {
  NOT_STARTED:        0,
  DOCUMENT_GATHERING: 1,
  SUBMITTED:          2,
  UNDER_REVIEW:       3,
  APPROVED:           4,
  REJECTED:           -1,
};

// ── Styling helpers ───────────────────────────────────────────────────────────

type StepState = 'completed' | 'active' | 'pending' | 'rejected';

function getStepState(
  stepId: WorkflowStatus,
  currentStatus: WorkflowStatus,
): StepState {
  if (currentStatus === 'REJECTED') {
    // REJECTED means the app was rejected after UNDER_REVIEW
    if (STATUS_RANK[stepId] < STATUS_RANK['UNDER_REVIEW']) return 'completed';
    if (stepId === 'UNDER_REVIEW') return 'rejected';
    return 'pending';
  }
  const currentRank = STATUS_RANK[currentStatus];
  const stepRank    = STATUS_RANK[stepId];
  if (stepRank < currentRank) return 'completed';
  if (stepRank === currentRank) return 'active';
  return 'pending';
}

const DOT_CLASSES: Record<StepState, string> = {
  completed: 'bg-emerald-500 border-emerald-500 text-white shadow-[0_0_12px_rgba(16,185,129,0.35)]',
  active:    'bg-industrial-accent border-industrial-accent text-white shadow-[0_0_16px_rgba(249,115,22,0.45)] ring-4 ring-industrial-accent/20',
  pending:   'bg-slate-100 border-slate-300 text-slate-400 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-500',
  rejected:  'bg-red-500/90 border-red-500 text-white shadow-[0_0_12px_rgba(239,68,68,0.4)]',
};

const LABEL_CLASSES: Record<StepState, string> = {
  completed: 'text-emerald-600 dark:text-emerald-400',
  active:    'text-slate-900 font-bold dark:text-white',
  pending:   'text-slate-400 dark:text-slate-500',
  rejected:  'text-red-600 font-bold dark:text-red-400',
};

const CONNECTOR_CLASSES: Record<'completed' | 'pending', string> = {
  completed: 'bg-emerald-500/70',
  pending:   'bg-slate-200 dark:bg-slate-700',
};

// ── Framer Motion variants ────────────────────────────────────────────────────

const dotVariant = {
  completed: { scale: 1,    transition: { type: 'spring' as const, stiffness: 300, damping: 20 } },
  active:    { scale: 1.12, transition: { type: 'spring' as const, stiffness: 300, damping: 20 } },
  pending:   { scale: 1,    transition: { type: 'spring' as const, stiffness: 300, damping: 20 } },
  rejected:  { scale: 1.12, transition: { type: 'spring' as const, stiffness: 300, damping: 20 } },
};

const fadeIn = {
  hidden: { opacity: 0, y: 8 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' as const } },
};

// ── Sub-components ────────────────────────────────────────────────────────────

function HorizontalConnector({ filled }: { filled: boolean }) {
  return (
    <div className="relative flex-1 h-0.5 mx-1 mt-5 hidden sm:block">
      <div className="absolute inset-0 rounded-full bg-slate-200 dark:bg-slate-700" />
      <motion.div
        className="absolute inset-y-0 left-0 rounded-full bg-emerald-500/70"
        initial={{ width: '0%' }}
        animate={{ width: filled ? '100%' : '0%' }}
        transition={{ duration: 0.5, ease: 'easeInOut' }}
      />
    </div>
  );
}

function VerticalConnector({ filled }: { filled: boolean }) {
  return (
    <div className="relative w-0.5 ml-4.5 my-0.5 h-8 sm:hidden">
      <div className="absolute inset-0 rounded-full bg-slate-200 dark:bg-slate-700" />
      <motion.div
        className="absolute inset-x-0 top-0 rounded-full bg-emerald-500/70"
        initial={{ height: '0%' }}
        animate={{ height: filled ? '100%' : '0%' }}
        transition={{ duration: 0.5, ease: 'easeInOut' }}
      />
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PermitStepper({
  currentStatus,
  permitName,
  authority,
  rejectionNote,
  forceVertical = false,
  className = '',
}: PermitStepperProps) {
  const isRejected = currentStatus === 'REJECTED';

  // For REJECTED we show 4 happy-path steps + the rejection indicator
  const visibleSteps: StepDef[] = isRejected
    ? [
        ...STEPS.slice(0, 4), // NOT_STARTED → UNDER_REVIEW
        {
          id:       'REJECTED',
          label:    'Rejected',
          sublabel: 'Re-submission required',
          icon:     XCircle,
        },
      ]
    : STEPS;

  return (
    <motion.div
      className={`rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-800 overflow-hidden ${className}`}
      initial="hidden"
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }}
    >
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      {(permitName || authority) && (
        <motion.div
          variants={fadeIn}
          className="px-5 py-4 border-b border-slate-200 dark:border-slate-700 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1"
        >
          <div>
            {permitName && (
              <p className="text-sm font-bold text-slate-900 dark:text-white">{permitName}</p>
            )}
            {authority && (
              <p className="text-xs text-slate-500 dark:text-slate-400">{authority}</p>
            )}
          </div>
          <StatusPill status={currentStatus} />
        </motion.div>
      )}

      {/* ── Stepper body ─────────────────────────────────────────────────────── */}
      <div className="px-5 py-6">
        {/* Horizontal layout (sm+) */}
        {!forceVertical && (
          <div className="hidden sm:flex items-start">
            {visibleSteps.map((step, idx) => {
              const state    = getStepState(step.id, currentStatus);
              const Icon     = step.icon;
              const isFilled = idx < visibleSteps.findIndex(
                (s) => getStepState(s.id, currentStatus) === 'active' || getStepState(s.id, currentStatus) === 'pending'
              );

              return (
                <div key={step.id} className="flex items-start flex-1">
                  <motion.div
                    className="flex flex-col items-center text-center flex-1"
                    variants={fadeIn}
                  >
                    {/* Dot */}
                    <motion.div
                      className={`flex h-9 w-9 items-center justify-center rounded-full border-2 transition-colors duration-300 ${DOT_CLASSES[state]}`}
                      variants={dotVariant}
                      animate={state}
                    >
                      <Icon className="h-4 w-4" />
                    </motion.div>
                    {/* Label */}
                    <p className={`mt-2 text-[11px] leading-tight transition-colors duration-300 ${LABEL_CLASSES[state]}`}>
                      {step.label}
                    </p>
                    <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5 max-w-20 leading-snug">
                      {step.sublabel}
                    </p>
                  </motion.div>

                  {/* Connector (except after last step) */}
                  {idx < visibleSteps.length - 1 && (
                    <HorizontalConnector filled={isFilled} />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Vertical layout (mobile always; desktop when forceVertical) */}
        <div className={forceVertical ? 'flex flex-col' : 'flex flex-col sm:hidden'}>
          {visibleSteps.map((step, idx) => {
            const state = getStepState(step.id, currentStatus);
            const Icon  = step.icon;
            const isFilled =
              idx <
              visibleSteps.findIndex(
                (s) =>
                  getStepState(s.id, currentStatus) === 'active' ||
                  getStepState(s.id, currentStatus) === 'pending',
              );

            return (
              <div key={step.id}>
                <motion.div className="flex items-center gap-3" variants={fadeIn}>
                  {/* Dot */}
                  <motion.div
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-300 ${DOT_CLASSES[state]}`}
                    variants={dotVariant}
                    animate={state}
                  >
                    <Icon className="h-4 w-4" />
                  </motion.div>
                  {/* Label */}
                  <div>
                    <p className={`text-sm leading-tight transition-colors duration-300 ${LABEL_CLASSES[state]}`}>
                      {step.label}
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">{step.sublabel}</p>
                  </div>
                </motion.div>

                {idx < visibleSteps.length - 1 && (
                  <VerticalConnector filled={isFilled} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Rejection note ────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {isRejected && rejectionNote && (
          <motion.div
            key="rejection-note"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1, transition: { duration: 0.25 } }}
            exit={{ height: 0, opacity: 0, transition: { duration: 0.18 } }}
            className="overflow-hidden"
          >
            <div className="mx-5 mb-5 flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 dark:border-red-500/25 dark:bg-red-500/8">
              <AlertCircle className="h-4 w-4 text-red-500 dark:text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-red-600 dark:text-red-400 mb-0.5">Rejection Note</p>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">{rejectionNote}</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Status pill (used in header) ──────────────────────────────────────────────

const PILL_CONFIG: Record<WorkflowStatus, { cls: string; label: string }> = {
  NOT_STARTED:        { cls: 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-700 dark:text-slate-400 dark:border-slate-600',   label: 'Not Started'         },
  DOCUMENT_GATHERING: { cls: 'bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-500/12 dark:text-amber-400 dark:border-amber-500/30',  label: 'Gathering Documents' },
  SUBMITTED:          { cls: 'bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/12 dark:text-blue-400 dark:border-blue-500/30',        label: 'Submitted'           },
  UNDER_REVIEW:       { cls: 'bg-violet-50 text-violet-600 border-violet-200 dark:bg-violet-500/12 dark:text-violet-400 dark:border-violet-500/30', label: 'Under Review'        },
  APPROVED:           { cls: 'bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/12 dark:text-emerald-400 dark:border-emerald-500/30', label: 'Approved'            },
  REJECTED:           { cls: 'bg-red-50 text-red-600 border-red-200 dark:bg-red-500/12 dark:text-red-400 dark:border-red-500/30',              label: 'Rejected'            },
};

export function StatusPill({ status }: { status: WorkflowStatus }) {
  const { cls, label } = PILL_CONFIG[status];
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  );
}
