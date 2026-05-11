'use client';

import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShieldCheck,
  FileText,
  Clock,
  Flame,
  Zap,
  Droplets,
  Map,
  ClipboardCheck,
  Building2,
  Leaf,
  HardHat,
  ChevronRight,
  TriangleAlert,
  BadgeCheck,
  Calculator,
  Layers,
  Info,
  Activity,
  ClipboardList,
  ShieldAlert,
} from 'lucide-react';
import PermitStepper from '@/components/PermitStepper';
import type { WorkflowStatus } from '@/components/PermitStepper';
import RiskAlertBanner from '@/components/RiskAlertBanner';
import type { RiskAlert } from '@/components/RiskAlertBanner';

// ── Types ──────────────────────────────────────────────────────────────────────

type ZoningType = 'RESIDENTIAL' | 'COMMERCIAL' | 'INDUSTRIAL' | 'MIXED_USE';
type ConstructionType = 'NEW_CONSTRUCTION' | 'EXTENSION' | 'RENOVATION' | 'DEMOLITION';
type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

interface BuildingParams {
  floorArea: string;
  stories: string;
  zoningType: ZoningType;
  constructionType: ConstructionType;
  projectValueLkr: string;
}

interface PermitRequirement {
  id: string;
  name: string;
  authority: string;
  icon: React.ElementType;
  estimatedFeeLkr: number;
  minDays: number;
  maxDays: number;
  mandatory: boolean;
  riskLevel: RiskLevel;
  description: string;
  requiredDocuments: string[];
  legalReference: string;
  phase: 1 | 2 | 3;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const ZONING_LABELS: Record<ZoningType, string> = {
  RESIDENTIAL: 'Residential',
  COMMERCIAL:  'Commercial',
  INDUSTRIAL:  'Industrial',
  MIXED_USE:   'Mixed-Use',
};

const CONSTRUCTION_LABELS: Record<ConstructionType, string> = {
  NEW_CONSTRUCTION: 'New Construction',
  EXTENSION:        'Extension / Addition',
  RENOVATION:       'Renovation / Fit-Out',
  DEMOLITION:       'Demolition',
};

const RISK_CONFIG: Record<RiskLevel, { badge: string; dot: string; label: string }> = {
  LOW:    { badge: 'bg-emerald-500/15 text-emerald-400', dot: 'bg-emerald-400', label: 'Low Risk'    },
  MEDIUM: { badge: 'bg-amber-500/15 text-amber-400',    dot: 'bg-amber-400',   label: 'Medium Risk' },
  HIGH:   { badge: 'bg-red-500/15 text-red-400',        dot: 'bg-red-400',     label: 'High Risk'   },
};

const PHASE_LABELS: Record<number, string> = {
  1: 'Phase 1 — Pre-Construction Approvals',
  2: 'Phase 2 — During Construction',
  3: 'Phase 3 — Completion & Occupancy',
};

const PHASE_ACCENT: Record<number, string> = {
  1: 'border-orange-200 bg-white',
  2: 'border-blue-200 bg-white',
  3: 'border-emerald-200 bg-white',
};

const PHASE_DOT: Record<number, string> = {
  1: 'bg-industrial-accent',
  2: 'bg-blue-400',
  3: 'bg-emerald-400',
};

// ── Permit Fee Calculators ─────────────────────────────────────────────────────

function calcUDAFee(area: number, zoning: ZoningType): number {
  const rates: Record<ZoningType, number> = {
    RESIDENTIAL: 50, COMMERCIAL: 100, INDUSTRIAL: 75, MIXED_USE: 85,
  };
  const mins: Record<ZoningType, number> = {
    RESIDENTIAL: 5_000, COMMERCIAL: 10_000, INDUSTRIAL: 15_000, MIXED_USE: 10_000,
  };
  return Math.max(area * rates[zoning], mins[zoning]);
}

function calcLocalAuthorityFee(area: number, zoning: ZoningType): number {
  const rates: Record<ZoningType, number> = {
    RESIDENTIAL: 35, COMMERCIAL: 65, INDUSTRIAL: 55, MIXED_USE: 55,
  };
  return Math.max(area * rates[zoning], 4_000);
}

function calcFireSafetyFee(area: number, stories: number): number {
  const base = stories >= 5 ? 80_000 : stories >= 3 ? 50_000 : 30_000;
  return base + area * 15;
}

// ── Permit Catalogue ──────────────────────────────────────────────────────────

function buildPermitList(params: BuildingParams): PermitRequirement[] {
  const area = parseFloat(params.floorArea) || 0;
  const stories = parseInt(params.stories, 10) || 1;
  const { zoningType: zoning, constructionType } = params;
  const isNew = constructionType === 'NEW_CONSTRUCTION';
  const isDemo = constructionType === 'DEMOLITION';

  const permits: PermitRequirement[] = [];

  // ── Phase 1 ────────────────────────────────────────────────────────────────

  // UDA Development Permission — always required for area > 100 sqm or new construction
  if (isNew || isDemo || area > 100) {
    permits.push({
      id:          'uda',
      name:        'UDA Development Permission',
      authority:   'Urban Development Authority (UDA)',
      icon:        Building2,
      estimatedFeeLkr: calcUDAFee(area, zoning),
      minDays:     21,
      maxDays:     60,
      mandatory:   true,
      riskLevel:   'HIGH',
      phase:       1,
      description: 'Statutory approval from the Urban Development Authority for any development within UDA-regulated zones.',
      requiredDocuments: [
        'Survey plan certified by Licensed Surveyor',
        'Architectural drawings (4 sets)',
        'Deed of title / lease agreement',
        'Structural drawings (for buildings > 3 stories)',
        'Completed Form UDA/DP/01',
      ],
      legalReference: 'Urban Development Authority Law No. 41 of 1978, Section 14',
    });
  }

  // Local Authority Building Plan Approval — always required
  permits.push({
    id:          'local-auth',
    name:        'Local Authority Building Plan Approval',
    authority:   'Municipal / Urban / Pradeshiya Sabha Council',
    icon:        ClipboardCheck,
    estimatedFeeLkr: calcLocalAuthorityFee(area, zoning),
    minDays:     14,
    maxDays:     45,
    mandatory:   true,
    riskLevel:   'HIGH',
    phase:       1,
    description: 'Building plan approval is mandatory before any construction activity. The relevant local authority verifies conformity with the building regulations.',
    requiredDocuments: [
      'Approved survey plan',
      'Architectural drawings (stamped by Chartered Architect)',
      'Structural design calculations',
      'Soil test report (for > 2 stories)',
      'Application form with owner signature',
    ],
    legalReference: 'Building Regulations 1986 under Local Authorities Ordinance, Section 23',
  });

  // CEA Environmental Clearance — for large or industrial projects
  if (area > 500 || zoning === 'INDUSTRIAL' || zoning === 'COMMERCIAL') {
    const feeTier = area > 2000 ? 150_000 : area > 500 ? 75_000 : 50_000;
    permits.push({
      id:          'cea',
      name:        'CEA Environmental Clearance',
      authority:   'Central Environmental Authority (CEA)',
      icon:        Leaf,
      estimatedFeeLkr: feeTier,
      minDays:     30,
      maxDays:     90,
      mandatory:   zoning === 'INDUSTRIAL',
      riskLevel:   'HIGH',
      phase:       1,
      description: 'Projects above 500 m² or in industrial/commercial zones require an environmental screening or Initial Environmental Examination (IEE).',
      requiredDocuments: [
        'Project Information Document (PID)',
        'Environmental Impact Assessment report',
        'Site plan showing buffer zones',
        'Drainage disposal plan',
        'EIA application form (CEA/EIA/01)',
      ],
      legalReference: 'National Environmental Act No. 47 of 1980, Section 23(cc)',
    });
  }

  // Road Development Authority Permit — commercial, industrial, or large site
  if (zoning === 'COMMERCIAL' || zoning === 'INDUSTRIAL' || area > 1000) {
    permits.push({
      id:          'rda',
      name:        'Road Access / Deviation Permit',
      authority:   'Road Development Authority (RDA)',
      icon:        Map,
      estimatedFeeLkr: zoning === 'INDUSTRIAL' ? 100_000 : 45_000,
      minDays:     14,
      maxDays:     30,
      mandatory:   false,
      riskLevel:   'MEDIUM',
      phase:       1,
      description: 'Required when construction activities involve or affect a national road, access deviation, or hoarding on a road reserve.',
      requiredDocuments: [
        'Site location plan',
        'Traffic impact assessment',
        'Proposed road access layout',
        'RDA application form',
      ],
      legalReference: 'Road Development Authority Act No. 73 of 1981, Section 8',
    });
  }

  // ── Phase 2 ────────────────────────────────────────────────────────────────

  // Fire Safety Certificate — commercial, 3+ stories, or large area
  if (stories >= 3 || area > 1000 || zoning === 'COMMERCIAL' || zoning === 'INDUSTRIAL') {
    permits.push({
      id:          'fire',
      name:        'Fire Safety Certificate',
      authority:   'Sri Lanka Fire Department / District Fire Brigade',
      icon:        Flame,
      estimatedFeeLkr: calcFireSafetyFee(area, stories),
      minDays:     10,
      maxDays:     30,
      mandatory:   stories >= 3 || zoning === 'COMMERCIAL',
      riskLevel:   stories >= 5 ? 'HIGH' : 'MEDIUM',
      phase:       2,
      description: 'Issued after inspection of fire suppression systems, emergency exits, fire-rated doors, and fire detection installations.',
      requiredDocuments: [
        'Fire protection system drawings',
        'Fire compartmentation plan',
        'Sprinkler system layout',
        'Emergency evacuation plan',
        'Hydrant installation certificate',
      ],
      legalReference: 'Fire Services Act No. 24 of 1974; SLSI SLS 1390 Fire Safety Standard',
    });
  }

  // Electrical Board Connection Approval
  if (isNew || constructionType === 'EXTENSION') {
    const electricFee = stories >= 3 ? 45_000 : 20_000;
    permits.push({
      id:          'electrical',
      name:        'Electrical Supply Connection Approval',
      authority:   'Lanka Electricity Company (LECO) / Ceylon Electricity Board (CEB)',
      icon:        Zap,
      estimatedFeeLkr: electricFee,
      minDays:     7,
      maxDays:     21,
      mandatory:   true,
      riskLevel:   'MEDIUM',
      phase:       2,
      description: 'Approval for new electrical supply connection, including load application and metering installation inspection.',
      requiredDocuments: [
        'Electrical installation drawings',
        'Single-line diagram',
        'Load calculation sheet',
        'Registered electrical contractor certification',
        'Completed CEB/LECO application form',
      ],
      legalReference: 'Electricity Act No. 20 of 2009, Section 44; IEE Wiring Regulations BS 7671',
    });
  }

  // Water & Drainage Board — new construction
  if (isNew || constructionType === 'EXTENSION') {
    permits.push({
      id:          'water',
      name:        'Water Supply & Drainage Connection',
      authority:   'National Water Supply & Drainage Board (NWSDB)',
      icon:        Droplets,
      estimatedFeeLkr: 25_000,
      minDays:     10,
      maxDays:     25,
      mandatory:   true,
      riskLevel:   'MEDIUM',
      phase:       2,
      description: 'Connection approval for potable water supply and sewage/drainage tie-in to the municipal network.',
      requiredDocuments: [
        'Plumbing layout drawings',
        'Sewage disposal plan',
        'Water demand calculation',
        'NWSDB application form',
      ],
      legalReference: 'National Water Supply & Drainage Board Law No. 2 of 1974, Section 15',
    });
  }

  // ── Phase 3 ────────────────────────────────────────────────────────────────

  // Certificate of Conformity — always required at the end
  permits.push({
    id:          'coc',
    name:        'Certificate of Conformity (CoC)',
    authority:   'Local Authority / Chartered Engineer',
    icon:        BadgeCheck,
    estimatedFeeLkr: 15_000,
    minDays:     7,
    maxDays:     21,
    mandatory:   true,
    riskLevel:   'HIGH',
    phase:       3,
    description: 'Issued by the local authority after final inspection confirms that all completed work conforms to the approved plans and building regulations.',
    requiredDocuments: [
      'As-built drawings',
      'Structural completion certificate (Chartered Engineer)',
      'Electrical inspection certificate',
      'Plumbing completion certificate',
      'Fire safety completion report',
    ],
    legalReference: 'Building Regulations 1986, Section 36; UDA Circular No. 2022/01',
  });

  // Occupancy Permit — commercial / multi-residential
  if (zoning === 'COMMERCIAL' || zoning === 'INDUSTRIAL' || stories >= 3) {
    permits.push({
      id:          'occupancy',
      name:        'Certificate of Occupancy',
      authority:   'Local Authority / UDA',
      icon:        HardHat,
      estimatedFeeLkr: 20_000,
      minDays:     14,
      maxDays:     30,
      mandatory:   true,
      riskLevel:   'HIGH',
      phase:       3,
      description: 'Authorises legal occupation of the building. Issued only after all Phase 1 & 2 clearances and the Certificate of Conformity are in order.',
      requiredDocuments: [
        'Certificate of Conformity',
        'Fire Safety Certificate',
        'LECO/CEB connection certificate',
        'NWSDB connection certificate',
        'Structural completion report',
      ],
      legalReference: 'Urban Development Authority Law No. 41 of 1978, Section 19; Building Regulations 1986, Section 38',
    });
  }

  return permits;
}

// ── Fee formatter ──────────────────────────────────────────────────────────────

function formatLKR(amount: number): string {
  return `LKR ${amount.toLocaleString('en-LK')}`;
}

// ── Animation variants ─────────────────────────────────────────────────────────

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show:   { opacity: 1, y: 0,  transition: { duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number] } },
};

const stagger = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.07 } },
};

const cardVariant = {
  hidden: { opacity: 0, y: 20, scale: 0.98 },
  show:   { opacity: 1, y: 0,  scale: 1, transition: { duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number] } },
  exit:   { opacity: 0, y: -10, scale: 0.97, transition: { duration: 0.2 } },
};

// ── Shared input class ─────────────────────────────────────────────────────────

const inputCls =
  'w-full bg-slate-50 border border-slate-300 rounded-lg px-3.5 py-2.5 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-industrial-accent focus:border-transparent transition-all duration-150';

const labelCls = 'block text-xs font-semibold text-slate-500 uppercase tracking-widest mb-1.5';

// ── Sub-components ─────────────────────────────────────────────────────────────

function SummaryBar({ permits }: { permits: PermitRequirement[] }) {
  const totalFee  = permits.reduce((s, p) => s + p.estimatedFeeLkr, 0);
  const maxDays   = permits.reduce((max, p) => Math.max(max, p.maxDays), 0);
  const mandatory = permits.filter((p) => p.mandatory).length;
  const highRisk  = permits.filter((p) => p.riskLevel === 'HIGH').length;

  return (
    <motion.div
      variants={fadeUp}
      className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6"
    >
      {[
        { icon: FileText,      label: 'Total Permits',   value: String(permits.length),  sub: `${mandatory} mandatory`     },
        { icon: Calculator,    label: 'Est. Total Fees', value: formatLKR(totalFee),     sub: 'Approximate',               },
        { icon: Clock,         label: 'Max Timeline',    value: `${maxDays} days`,        sub: 'Parallel processing'        },
        { icon: TriangleAlert, label: 'High-Risk Items', value: String(highRisk),         sub: 'Require immediate action'   },
      ].map(({ icon: Icon, label, value, sub }) => (
        <div
          key={label}
          className="rounded-xl border border-slate-200 bg-white shadow-sm px-4 py-3.5 flex flex-col gap-1"
        >
          <div className="flex items-center gap-1.5 text-slate-500">
            <Icon className="h-3.5 w-3.5 text-industrial-accent" />
            <span className="text-[10px] font-semibold uppercase tracking-widest">{label}</span>
          </div>
          <p className="text-base font-bold text-slate-900 leading-tight">{value}</p>
          <p className="text-[10px] text-slate-500">{sub}</p>
        </div>
      ))}
    </motion.div>
  );
}

function PhaseGroup({ phase, permits }: { phase: number; permits: PermitRequirement[] }) {
  if (permits.length === 0) return null;

  return (
    <div className="mb-5">
      <div className="flex items-center gap-2 mb-3">
        <span className={`h-2 w-2 rounded-full ${PHASE_DOT[phase]}`} />
        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-500">
          {PHASE_LABELS[phase]}
        </h3>
        <div className="flex-1 h-px bg-slate-200" />
      </div>
      <motion.div className="space-y-2.5" variants={stagger} initial="hidden" animate="show">
        {permits.map((permit) => (
          <PermitCard key={permit.id} permit={permit} />
        ))}
      </motion.div>
    </div>
  );
}

function PermitCard({ permit }: { permit: PermitRequirement }) {
  const [expanded, setExpanded] = useState(false);
  const { badge, dot, label } = RISK_CONFIG[permit.riskLevel];
  const Icon = permit.icon;

  return (
    <motion.div
      variants={cardVariant}
      layout
      className={`rounded-xl border ${PHASE_ACCENT[permit.phase]} overflow-hidden`}
    >
      {/* Header row */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full text-left px-4 py-3.5 flex items-center gap-3 group"
      >
        {/* Icon */}
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 border border-slate-200">
          <Icon className="h-4 w-4 text-industrial-accent" />
        </span>

        {/* Title + authority */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-slate-900 leading-tight">{permit.name}</p>
            {permit.mandatory && (
              <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-orange-100 text-industrial-accent">
                Required
              </span>
            )}
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5 truncate">{permit.authority}</p>
        </div>

        {/* Fee + days */}
        <div className="hidden sm:flex flex-col items-end gap-0.5 shrink-0">
          <p className="text-sm font-bold text-slate-900 tabular-nums">{formatLKR(permit.estimatedFeeLkr)}</p>
          <p className="text-[11px] text-slate-500">{permit.minDays}–{permit.maxDays} days</p>
        </div>

        {/* Risk badge */}
        <span className={`hidden sm:inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${badge} shrink-0`}>
          <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
          {label}
        </span>

        {/* Expand chevron */}
        <ChevronRight
          className={`h-4 w-4 text-slate-400 shrink-0 transition-transform duration-200 group-hover:text-slate-700 ${expanded ? 'rotate-90' : ''}`}
        />
      </button>

      {/* Mobile: fee + risk row */}
      <div className="sm:hidden flex items-center justify-between px-4 pb-3 -mt-1">
        <p className="text-sm font-bold text-slate-900">{formatLKR(permit.estimatedFeeLkr)}</p>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-slate-500">{permit.minDays}–{permit.maxDays} days</span>
          <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${badge}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
            {label}
          </span>
        </div>
      </div>

      {/* Expanded detail */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1, transition: { duration: 0.25, ease: 'easeOut' } }}
            exit={{ height: 0, opacity: 0, transition: { duration: 0.18, ease: 'easeIn' } }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1 border-t border-slate-200 grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Description */}
              <div className="sm:col-span-2 flex gap-2">
                <Info className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
                <p className="text-xs text-slate-600 leading-relaxed">{permit.description}</p>
              </div>

              {/* Required documents */}
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
                  Required Documents
                </p>
                <ul className="space-y-1">
                  {permit.requiredDocuments.map((doc) => (
                    <li key={doc} className="flex items-start gap-1.5 text-xs text-slate-700">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-industrial-accent shrink-0" />
                      {doc}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Legal reference */}
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
                  Legal Reference
                </p>
                <p className="text-xs text-slate-700 leading-relaxed font-mono bg-slate-50 rounded-md px-3 py-2 border border-slate-200">
                  {permit.legalReference}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Demo / mock data ─────────────────────────────────────────────────────────
// Replace these with data fetched from:
//   GET  /api/v1/compliance/{project_id}/status  → permit statuses
//   POST /api/v1/compliance/analyze-risk         → risk deviations

interface LivePermitStatus {
  id:           string;
  name:         string;
  authority:    string;
  status:       WorkflowStatus;
  rejectionNote?: string;
}

const DEMO_PERMIT_STATUSES: LivePermitStatus[] = [
  {
    id:        'uda',
    name:      'UDA Development Permission',
    authority: 'Urban Development Authority (UDA)',
    status:    'UNDER_REVIEW',
  },
  {
    id:        'local-auth',
    name:      'Local Authority Building Plan Approval',
    authority: 'Municipal / Urban / Pradeshiya Sabha Council',
    status:    'APPROVED',
  },
  {
    id:        'cea',
    name:      'CEA Environmental Clearance',
    authority: 'Central Environmental Authority (CEA)',
    status:    'SUBMITTED',
  },
  {
    id:        'fire',
    name:      'Fire Safety Certificate',
    authority: 'Sri Lanka Fire Department',
    status:    'DOCUMENT_GATHERING',
  },
  {
    id:           'rda',
    name:         'Road Access / Deviation Permit',
    authority:    'Road Development Authority (RDA)',
    status:       'REJECTED',
    rejectionNote: 'Submitted traffic impact assessment does not meet the minimum scope required for a Category B road. Please commission a full traffic study and resubmit.',
  },
];

const DEMO_RISK_ALERTS: RiskAlert[] = [
  {
    id:              'risk-001',
    severity:        'CRITICAL',
    title:           'Foundation Work Without UDA Approval',
    message:         'Physical foundation activity has been detected on site (FOUNDATION_STARTED stage) while UDA Development Permission remains Under Review. This constitutes an unauthorised commencement of works.',
    penaltyLkr:      500_000,
    dailyAccrualLkr: 10_000,
    stopWork:        true,
    statute:         'Urban Development Authority Law No. 41 of 1978, Section 14; Building Regulations 1986, Section 8',
    correctiveAction: 'Immediately halt all foundation and excavation work. Submit an urgent representation to the UDA with a site inspection request. Resume only upon written approval from the Authority.',
  },
  {
    id:              'risk-002',
    severity:        'HIGH',
    title:           'Road Access Permit Rejected — Active Site Hoarding',
    message:         'The RDA Road Access / Deviation Permit application was rejected, but site hoarding on the road reserve remains in place. Continued occupation is a statutory violation.',
    penaltyLkr:      250_000,
    dailyAccrualLkr: 5_000,
    stopWork:        false,
    statute:         'Road Development Authority Act No. 73 of 1981, Section 8',
    correctiveAction: 'Remove all hoarding from the road reserve immediately. Engage a transport engineer to address the gaps in the traffic impact assessment before resubmitting.',
  },
  {
    id:              'risk-003',
    severity:        'MEDIUM',
    title:           'CEA Clearance Pending — Site Drainage Works Commenced',
    message:         'Drainage diversion works have commenced on site before CEA Environmental Clearance has been granted. This may constitute a violation of the National Environmental Act.',
    penaltyLkr:      75_000,
    dailyAccrualLkr: 1_000,
    stopWork:        false,
    statute:         'National Environmental Act No. 47 of 1980, Section 23(cc)',
    correctiveAction: 'Pause drainage modification works. Ensure all site runoff controls are in place. Expedite the IEE submission to CEA and seek interim written confirmation of acceptable site management.',
  },
  {
    id:       'risk-004',
    severity: 'LOW',
    title:    'Fire Safety Documents Not Yet Initiated',
    message:  'Project has advanced to structural framing stage but the Fire Safety Certificate application is still at Document Gathering phase. Early engagement with the Fire Department is recommended.',
    statute:  'Fire Services Act No. 24 of 1974; SLSI SLS 1390',
    correctiveAction: 'Appoint a fire safety consultant and commence preparation of fire protection system drawings and evacuation plans. Submit the Fire Safety Certificate application before roofing begins.',
  },
];

// ── Tab bar config ─────────────────────────────────────────────────────────────

type DashboardTab = 'roadmap' | 'progress' | 'risk';

interface TabConfig {
  id:       DashboardTab;
  label:    string;
  icon:     React.ElementType;
  alertDot?: boolean;
}

const TABS: TabConfig[] = [
  { id: 'roadmap',  label: 'Approval Roadmap', icon: ClipboardList               },
  { id: 'progress', label: 'Live Progress',    icon: Activity                    },
  { id: 'risk',     label: 'Risk Warnings',    icon: ShieldAlert, alertDot: true },
];

// ── Main Component ─────────────────────────────────────────────────────────────

const DEFAULT_PARAMS: BuildingParams = {
  floorArea:        '',
  stories:          '',
  zoningType:       'RESIDENTIAL',
  constructionType: 'NEW_CONSTRUCTION',
  projectValueLkr:  '',
};

export default function ComplianceRoadmap({ activeView }: { activeView?: DashboardTab }) {
  const [activeTab, setActiveTab] = useState<DashboardTab>(activeView ?? 'roadmap');
  const [params, setParams]     = useState<BuildingParams>(DEFAULT_PARAMS);
  const [generated, setGenerated] = useState(false);
  const [errors, setErrors]     = useState<Partial<Record<keyof BuildingParams, string>>>({});
  const [riskAlerts, setRiskAlerts] = useState<RiskAlert[]>(DEMO_RISK_ALERTS);
  const [liveStatuses] = useState<LivePermitStatus[]>(DEMO_PERMIT_STATUSES);

  function update<K extends keyof BuildingParams>(key: K, val: BuildingParams[K]) {
    setParams((p) => ({ ...p, [key]: val }));
    setErrors((e) => ({ ...e, [key]: undefined }));
  }

  function validate(): boolean {
    const next: typeof errors = {};
    if (!params.floorArea || parseFloat(params.floorArea) <= 0)
      next.floorArea = 'Enter a valid floor area.';
    if (!params.stories || parseInt(params.stories, 10) < 1)
      next.stories = 'Enter a valid number of stories.';
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setGenerated(true);
  }

  function handleReset() {
    setParams(DEFAULT_PARAMS);
    setErrors({});
    setGenerated(false);
  }

  const permits = useMemo(
    () => (generated ? buildPermitList(params) : []),
    [generated, params],
  );

  const byPhase = useMemo(() => {
    const map: Record<number, PermitRequirement[]> = { 1: [], 2: [], 3: [] };
    for (const p of permits) map[p.phase].push(p);
    return map;
  }, [permits]);

  return (
    <motion.div
      className="space-y-6"
      initial="hidden"
      animate="show"
      variants={stagger}
    >
      {/* ── Page header ──────────────────────────────────────────────────────── */}
      <motion.div variants={fadeUp}>
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-industrial-accent/10 border border-industrial-accent/20">
            <ShieldCheck className="h-5 w-5 text-industrial-accent" />
          </span>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Compliance Module
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Approval roadmap, live permit tracking, and proactive risk monitoring for your project.
            </p>
          </div>
        </div>
      </motion.div>

      {/* ── Top Tab Bar ──────────────────────────────────────────────────────── */}
      <motion.div variants={fadeUp}>
        <div className="relative flex items-center gap-1 rounded-xl border border-slate-200 bg-white shadow-sm p-1 w-fit">
          {TABS.map(({ id, label, icon: TabIcon, alertDot }) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveTab(id)}
              className={`relative flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors duration-150 z-10 ${
                activeTab === id
                  ? 'text-industrial-accent'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {activeTab === id && (
                <motion.span
                  layoutId="tab-pill"
                  className="absolute inset-0 rounded-lg bg-industrial-accent/10 border border-industrial-accent/25"
                  transition={{ type: 'spring', stiffness: 400, damping: 35 }}
                />
              )}
              <TabIcon className="relative h-4 w-4 shrink-0" />
              <span className="relative leading-none">{label}</span>
              {alertDot && (
                <span className="relative flex h-2 w-2 shrink-0">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500" />
                </span>
              )}
            </button>
          ))}
        </div>
      </motion.div>

      {/* ── View content ──────────────────────────────────────────────────────── */}
      <AnimatePresence mode="wait">

      {activeTab === 'roadmap' && (
      <motion.div key="roadmap" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.22 }}>
      {/* ── Two-column layout ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-6 items-start">

        {/* ── LEFT COLUMN: Parameter form ──────────────────────────────────────── */}
        <motion.div variants={fadeUp} className="xl:sticky xl:top-6">
          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            {/* Card header */}
            <div className="px-5 py-4 border-b border-slate-200 flex items-center gap-2">
              <Layers className="h-4 w-4 text-industrial-accent" />
              <h2 className="text-sm font-bold text-slate-900 tracking-tight">Building Parameters</h2>
            </div>

            <form onSubmit={handleGenerate} className="px-5 py-5 space-y-5">
              {/* Floor Area */}
              <div>
                <label className={labelCls}>Total Floor Area (m²)</label>
                <input
                  type="number"
                  min="1"
                  step="1"
                  placeholder="e.g. 450"
                  value={params.floorArea}
                  onChange={(e) => update('floorArea', e.target.value)}
                  className={`${inputCls} ${errors.floorArea ? 'ring-2 ring-red-500 border-red-500' : ''}`}
                />
                {errors.floorArea && (
                  <p className="mt-1 text-xs text-red-400">{errors.floorArea}</p>
                )}
              </div>

              {/* Number of Stories */}
              <div>
                <label className={labelCls}>Number of Stories</label>
                <input
                  type="number"
                  min="1"
                  max="50"
                  step="1"
                  placeholder="e.g. 3"
                  value={params.stories}
                  onChange={(e) => update('stories', e.target.value)}
                  className={`${inputCls} ${errors.stories ? 'ring-2 ring-red-500 border-red-500' : ''}`}
                />
                {errors.stories && (
                  <p className="mt-1 text-xs text-red-400">{errors.stories}</p>
                )}
              </div>

              {/* Zoning Type */}
              <div>
                <label className={labelCls}>Zoning Classification</label>
                <select
                  value={params.zoningType}
                  onChange={(e) => update('zoningType', e.target.value as ZoningType)}
                  className={inputCls}
                >
                  {(Object.keys(ZONING_LABELS) as ZoningType[]).map((z) => (
                    <option key={z} value={z}>{ZONING_LABELS[z]}</option>
                  ))}
                </select>
              </div>

              {/* Construction Type */}
              <div>
                <label className={labelCls}>Construction Type</label>
                <select
                  value={params.constructionType}
                  onChange={(e) => update('constructionType', e.target.value as ConstructionType)}
                  className={inputCls}
                >
                  {(Object.keys(CONSTRUCTION_LABELS) as ConstructionType[]).map((c) => (
                    <option key={c} value={c}>{CONSTRUCTION_LABELS[c]}</option>
                  ))}
                </select>
              </div>

              {/* Project Value */}
              <div>
                <label className={labelCls}>Estimated Project Value (LKR) <span className="normal-case font-normal opacity-60">— optional</span></label>
                <input
                  type="number"
                  min="1"
                  step="1000"
                  placeholder="e.g. 25,000,000"
                  value={params.projectValueLkr}
                  onChange={(e) => update('projectValueLkr', e.target.value)}
                  className={inputCls}
                />
                <p className="mt-1 text-[10px] text-slate-500">
                  Used to calculate percentage-based regulatory penalties if compliance deviations are detected.
                </p>
              </div>

              {/* Divider */}
              <div className="h-px bg-slate-200" />

              {/* Actions */}
              <div className="flex flex-col gap-2.5">
                <button
                  type="submit"
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-industrial-accent hover:bg-industrial-accent-hover text-white text-sm font-bold px-4 py-2.5 transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-industrial-accent focus-visible:ring-offset-2 focus-visible:ring-offset-white"
                >
                  <ShieldCheck className="h-4 w-4" />
                  Generate Permit Roadmap
                </button>
                {generated && (
                  <button
                    type="button"
                    onClick={handleReset}
                    className="w-full text-center text-xs text-slate-500 hover:text-slate-700 transition-colors duration-150 py-1"
                  >
                    Reset Parameters
                  </button>
                )}
              </div>
            </form>

            {/* Info footer */}
            <div className="px-5 py-3.5 border-t border-slate-200 bg-slate-50 flex items-start gap-2">
              <Info className="h-3.5 w-3.5 text-slate-400 shrink-0 mt-0.5" />
              <p className="text-[10px] text-slate-500 leading-relaxed">
                Fee estimates are indicative only and based on current Sri Lankan building authority schedules. Actual fees may vary. Consult a Licensed Architect before submission.
              </p>
            </div>
          </div>
        </motion.div>

        {/* ── RIGHT COLUMN: Roadmap ────────────────────────────────────────────── */}
        <div className="min-w-0">
          <AnimatePresence mode="wait">
            {!generated ? (
              /* ── Empty state ─────────────────────────────────────────────── */
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, transition: { duration: 0.15 } }}
                className="flex flex-col items-center justify-center gap-5 rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 py-28 text-center px-8"
              >
                <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-orange-50 border border-orange-200">
                  <ClipboardCheck className="h-8 w-8 text-industrial-accent" />
                </span>
                <div>
                  <p className="text-base font-semibold text-slate-700">
                    Your Approval Roadmap Will Appear Here
                  </p>
                  <p className="mt-1.5 text-sm text-slate-500 max-w-sm mx-auto leading-relaxed">
                    Fill in the building parameters on the left and click{' '}
                    <span className="text-industrial-accent font-semibold">Generate Permit Roadmap</span>{' '}
                    to see the full required approvals, fees, and timelines.
                  </p>
                </div>
              </motion.div>
            ) : (
              /* ── Roadmap ────────────────────────────────────────────────── */
              <motion.div
                key="roadmap"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, transition: { duration: 0.15 } }}
              >
                <motion.div
                  initial="hidden"
                  animate="show"
                  variants={stagger}
                  className="space-y-2"
                >
                  {/* Summary bar */}
                  <SummaryBar permits={permits} />

                  {/* Phase label + parameter recap */}
                  <motion.div
                    variants={fadeUp}
                    className="flex flex-wrap items-center gap-2 mb-4 px-0.5"
                  >
                    {[
                      `${params.floorArea} m²`,
                      `${params.stories} ${parseInt(params.stories, 10) === 1 ? 'Story' : 'Stories'}`,
                      ZONING_LABELS[params.zoningType],
                      CONSTRUCTION_LABELS[params.constructionType],
                    ].map((tag) => (
                      <span
                        key={tag}
                        className="text-[11px] font-semibold px-2.5 py-1 rounded-full bg-slate-100 border border-slate-200 text-slate-500"
                      >
                        {tag}
                      </span>
                    ))}
                  </motion.div>

                  {/* Phase groups */}
                  <motion.div variants={fadeUp} className="space-y-6">
                    {[1, 2, 3].map((phase) => (
                      <PhaseGroup
                        key={phase}
                        phase={phase}
                        permits={byPhase[phase] ?? []}
                      />
                    ))}
                  </motion.div>

                  {/* Footer note */}
                  <motion.div
                    variants={fadeUp}
                    className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3.5 mt-2"
                  >
                    <TriangleAlert className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-slate-600 leading-relaxed">
                      Permits should be processed in order where possible. Some Phase 2 permits can run in parallel with Phase 1 reviews. A Licensed Architect or Project Manager should coordinate submission timelines. Switch to{' '}
                      <button type="button" onClick={() => setActiveTab('risk')} className="text-industrial-accent font-medium hover:underline focus:outline-none">Risk Warnings</button>{' '}
                      to view active compliance deviations.
                    </p>
                  </motion.div>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
      </motion.div>
      )}

      {/* ── Live Progress view ───────────────────────────────────────────────── */}
      {activeTab === 'progress' && (
        <motion.div
          key="progress"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.22 }}
          className="space-y-4"
        >
          {/* Section header */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10 border border-blue-500/20">
                <Activity className="h-4 w-4 text-blue-400" />
              </span>
              <div>
                <h2 className="text-sm font-bold text-slate-900">Live Permit Progress</h2>
                <p className="text-[10px] text-slate-500">
                  Real-time workflow status for each permit application.
                  {/* Bind: replace DEMO_PERMIT_STATUSES with data from GET /api/v1/compliance/{'{'}project_id{'}'}/status */}
                </p>
              </div>
            </div>
            {/* Progress summary pills */}
            <div className="flex flex-wrap gap-2">
              {(['APPROVED', 'UNDER_REVIEW', 'SUBMITTED', 'DOCUMENT_GATHERING', 'REJECTED'] as WorkflowStatus[]).map((s) => {
                const count = liveStatuses.filter((p) => p.status === s).length;
                if (count === 0) return null;
                const pill: Record<WorkflowStatus, string> = {
                  APPROVED:           'bg-emerald-500/12 text-emerald-400 border-emerald-500/25',
                  UNDER_REVIEW:       'bg-violet-500/12 text-violet-400 border-violet-500/25',
                  SUBMITTED:          'bg-blue-500/12 text-blue-400 border-blue-500/25',
                  DOCUMENT_GATHERING: 'bg-amber-500/12 text-amber-400 border-amber-500/25',
                  NOT_STARTED:        'bg-slate-100 text-slate-500 border-slate-200',
                  REJECTED:           'bg-red-500/12 text-red-400 border-red-500/25',
                };
                const pillLabel: Record<WorkflowStatus, string> = {
                  APPROVED: 'Approved', UNDER_REVIEW: 'Under Review', SUBMITTED: 'Submitted',
                  DOCUMENT_GATHERING: 'Gathering', NOT_STARTED: 'Not Started', REJECTED: 'Rejected',
                };
                return (
                  <span key={s} className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${pill[s]}`}>
                    {count} {pillLabel[s]}
                  </span>
                );
              })}
            </div>
          </div>

          {/* One stepper per permit */}
          <motion.div
            className="space-y-4"
            initial="hidden"
            animate="show"
            variants={{ hidden: {}, show: { transition: { staggerChildren: 0.08 } } }}
          >
            {liveStatuses.map((permit) => (
              <motion.div
                key={permit.id}
                variants={{
                  hidden: { opacity: 0, y: 16 },
                  show:   { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' as const } },
                }}
              >
                <PermitStepper
                  currentStatus={permit.status}
                  permitName={permit.name}
                  authority={permit.authority}
                  rejectionNote={permit.rejectionNote}
                />
              </motion.div>
            ))}
          </motion.div>

          {/* Empty state */}
          {liveStatuses.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 py-20 text-center">
              <Activity className="h-8 w-8 text-slate-400" />
              <p className="text-sm text-slate-500">
                No permit applications found for this project.<br />
                Initialise a project via{' '}
                <code className="text-industrial-accent text-xs">POST /api/v1/compliance/&#123;project_id&#125;/init</code>.
              </p>
            </div>
          )}
        </motion.div>
      )}

      {/* ── Risk Warnings tab ────────────────────────────────────────────────── */}
      {activeTab === 'risk' && (
        <motion.div
          key="risk"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.22 }}
        >
          {/*
            Backend binding:
            POST /api/v1/compliance/analyze-risk
            Body: { project_id: string } or { permits: PermitStatusInput[] }
            Map response.deviations → RiskAlert[] before passing to RiskAlertBanner.
          */}
          <RiskAlertBanner
            alerts={riskAlerts}
            projectName="Demo Project — Commercial Block A"
            onDismiss={(id) => setRiskAlerts((prev) => prev.filter((a) => a.id !== id))}
          />
        </motion.div>
      )}

      </AnimatePresence>
    </motion.div>
  );
}
