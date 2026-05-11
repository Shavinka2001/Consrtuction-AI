'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import {
  ScanSearch,
  AlertTriangle,
  Zap,
  X,
  ChevronRight,
  UploadCloud,
  Download,
} from 'lucide-react';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

// ── Types ──────────────────────────────────────────────────────────────────

type Severity = 'High' | 'Medium' | 'Low';

interface BoundingBox {
  id: string;
  top: number;
  left: number;
  width: number;
  height: number;
  label: string;
  severity: Severity;
}

interface ClashItem {
  id: string;
  elements: string;
  severity: Severity;
  location: string;
  x: number;
  y: number;
  imgWidth: number;
  imgHeight: number;
}

interface AnalysisDetection {
  class_name: string;
  confidence: number;
  bbox: { x_min: number; y_min: number; x_max: number; y_max: number };
}

interface StoredAnalysis {
  success: boolean;
  filename: string;
  detections: AnalysisDetection[];
  total_detections: number;
  blueprintUrl: string | null;
  imageWidth?: number;
  imageHeight?: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function toSeverity(confidence: number): Severity {
  if (confidence >= 0.7) return 'High';
  if (confidence >= 0.4) return 'Medium';
  return 'Low';
}

function getProfessionalLocation(
  x: number,
  y: number,
  originalWidth: number,
  originalHeight: number,
): { sector: string; pctX: number; pctY: number } {
  const pctX = parseFloat(((x / originalWidth) * 100).toFixed(1));
  const pctY = parseFloat(((y / originalHeight) * 100).toFixed(1));

  const hZone = pctX <= 33 ? 'Left' : pctX <= 66 ? 'Center' : 'Right';
  const vZone = pctY <= 33 ? 'Top'  : pctY <= 66 ? 'Middle' : 'Bottom';

  const sector =
    vZone === 'Middle' && hZone === 'Center'
      ? 'Center Area'
      : `${vZone}-${hZone} Area`;

  return { sector, pctX, pctY };
}

// ── Constants ──────────────────────────────────────────────────────────────

const SEVERITY_BOX: Record<Severity, string> = {
  High:   'border-red-500 bg-red-500/10',
  Medium: 'border-yellow-400 bg-yellow-400/10',
  Low:    'border-blue-400 bg-blue-400/10',
};

const SEVERITY_LABEL: Record<Severity, string> = {
  High:   'bg-red-500 text-white',
  Medium: 'bg-yellow-400 text-black',
  Low:    'bg-blue-400 text-white',
};

const SEVERITY_BADGE: Record<Severity, string> = {
  High:   'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',
  Medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-400/20 dark:text-yellow-300',
  Low:    'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
};

const SEVERITY_ICON: Record<Severity, string> = {
  High:   'text-red-500',
  Medium: 'text-yellow-400',
  Low:    'text-blue-400',
};

// ── Sub-components ─────────────────────────────────────────────────────────

function ClashBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${SEVERITY_BADGE[severity]}`}
    >
      {severity}
    </span>
  );
}

function AnnotatedBlueprint({
  blueprintUrl,
  boxes,
  hoveredIssueId,
}: {
  blueprintUrl: string;
  boxes: BoundingBox[];
  hoveredIssueId: string | null;
}) {
  return (
    <div
      className="relative w-full overflow-hidden rounded-lg bg-gray-100 dark:bg-industrial-surface-2"
      style={{ aspectRatio: '4/3' }}
    >
      <Image
        src={blueprintUrl}
        alt="Annotated blueprint"
        fill
        className="object-contain p-2"
        unoptimized={blueprintUrl.startsWith('blob:')}
      />
      {boxes.map((box) => {
        const isHovered = box.id === hoveredIssueId;
        const isDimmed  = hoveredIssueId !== null && !isHovered;
        const opacityClass = isDimmed ? 'opacity-20' : isHovered ? 'opacity-100' : 'opacity-40';
        const zClass       = isHovered ? 'z-10' : 'z-0';
        const borderClass  = isHovered ? 'border-4' : 'border-2';

        return (
          <div
            key={box.id}
            className={`absolute rounded ${borderClass} ${SEVERITY_BOX[box.severity]} ${opacityClass} ${zClass} transition-all duration-300`}
            style={{
              top:    `${box.top}%`,
              left:   `${box.left}%`,
              width:  `${box.width}%`,
              height: `${box.height}%`,
            }}
          >
            <span
              className={`absolute -top-5 left-0 whitespace-nowrap rounded-t px-1.5 py-0.5 text-[10px] font-bold leading-tight transition-all duration-300 ${SEVERITY_LABEL[box.severity]} ${isHovered ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
            >
              {box.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ClashList({
  clashes,
  onSelect,
  onHover,
}: {
  clashes: ClashItem[];
  onSelect: (item: ClashItem) => void;
  onHover: (id: string | null) => void;
}) {
  if (clashes.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-400 dark:text-industrial-muted">
        No issues detected.
      </p>
    );
  }

  return (
    <ul className="space-y-1.5">
      {clashes.map((clash) => (
        <li key={clash.id}>
          <button
            onClick={() => onSelect(clash)}
            onMouseEnter={() => onHover(clash.id)}
            onMouseLeave={() => onHover(null)}
            className="w-full flex items-center gap-2.5 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2.5 text-left hover:border-industrial-accent hover:bg-orange-50/40 dark:border-industrial-border dark:bg-industrial-surface-2 dark:hover:border-industrial-accent dark:hover:bg-industrial-accent-subtle/30 transition-colors group"
          >
            <AlertTriangle
              className={`h-3.5 w-3.5 shrink-0 ${SEVERITY_ICON[clash.severity]}`}
            />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-gray-900 dark:text-industrial-text truncate">
                {clash.elements.charAt(0).toUpperCase() +
                  clash.elements.slice(1).replace(/_/g, ' ')}
              </p>
              <p className="text-[10px] font-mono text-gray-400 dark:text-industrial-muted truncate">
                {clash.id} · {clash.location}
              </p>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <ClashBadge severity={clash.severity} />
              <ChevronRight className="h-3.5 w-3.5 text-gray-300 group-hover:text-industrial-accent transition-colors dark:text-industrial-muted" />
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}

function IssueDrawer({
  issue,
  onClose,
  aiRecommendation,
  isGenerating,
}: {
  issue: ClashItem | null;
  onClose: () => void;
  aiRecommendation: string | null;
  isGenerating: boolean;
}) {
  const [assignee, setAssignee] = useState('');

  if (!issue) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Issue Details"
        className="fixed inset-y-0 right-0 w-full md:w-95 bg-white shadow-2xl z-50 flex flex-col dark:bg-industrial-surface"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-gray-100 dark:border-industrial-border px-5 py-4">
          <div className="min-w-0">
            <p className="text-[10px] font-mono font-semibold text-gray-400 dark:text-industrial-muted mb-0.5">
              {issue.id}
            </p>
            <h2 className="text-base font-bold text-gray-900 dark:text-industrial-text leading-snug">
              {issue.elements.charAt(0).toUpperCase() +
                issue.elements.slice(1).replace(/_/g, ' ')}
            </h2>
            <span
              className={`inline-flex items-center mt-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${SEVERITY_BADGE[issue.severity]}`}
            >
              {issue.severity} Severity
            </span>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-industrial-nav-hover dark:hover:text-industrial-text transition-colors"
            aria-label="Close drawer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Location */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-industrial-muted">
              Location Details
            </h3>
            <div className="rounded-lg border border-gray-100 dark:border-industrial-border bg-gray-50 dark:bg-industrial-surface-2 p-3 space-y-2">
              {(() => {
                const { sector, pctX, pctY } = getProfessionalLocation(
                  issue.x,
                  issue.y,
                  issue.imgWidth,
                  issue.imgHeight,
                );
                return (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-industrial-muted">
                        Sector
                      </span>
                      <span className="font-mono text-sm font-bold text-gray-900 dark:text-industrial-text">
                        {sector}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-industrial-muted">
                        Position
                      </span>
                      <span className="font-mono text-sm font-bold text-gray-900 dark:text-industrial-text">
                        {pctX}%, {pctY}%
                      </span>
                    </div>
                  </>
                );
              })()}
            </div>
          </section>

          {/* AI Recommendation */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-industrial-muted">
              AI Recommendation
            </h3>
            <div className="rounded-lg border border-indigo-100 bg-indigo-50 dark:border-indigo-500/20 dark:bg-indigo-500/10 p-3.5">
              {isGenerating ? (
                <div className="flex items-start gap-2.5">
                  <div className="mt-0.5 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-500" />
                  <div className="flex-1 space-y-2">
                    <p className="text-xs font-medium text-indigo-500 animate-pulse">
                      AI is analyzing structural context…
                    </p>
                    <div className="h-2.5 w-full animate-pulse rounded bg-indigo-100 dark:bg-indigo-500/20" />
                    <div className="h-2.5 w-4/5 animate-pulse rounded bg-indigo-100 dark:bg-indigo-500/20" />
                    <div className="h-2.5 w-3/5 animate-pulse rounded bg-indigo-100 dark:bg-indigo-500/20" />
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  <Zap className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
                  <p className="text-sm text-indigo-800 dark:text-indigo-300 leading-relaxed">
                    <span className="font-semibold">AI Suggestion: </span>
                    {aiRecommendation ??
                      "Click an issue to generate a recommendation."}
                  </p>
                </div>
              )}
            </div>
          </section>

          {/* Assignee */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-industrial-muted">
              Assignee
            </h3>
            <select
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              className="w-full rounded-lg border border-gray-200 dark:border-industrial-border bg-white dark:bg-industrial-surface-2 px-3 py-2 text-sm text-gray-700 dark:text-industrial-text shadow-sm focus:border-industrial-accent focus:outline-none focus:ring-1 focus:ring-industrial-accent"
            >
              <option value="">— Select Assignee —</option>
              <option value="site-engineer">Site Engineer</option>
              <option value="architect">Architect</option>
            </select>
          </section>
        </div>

        {/* Footer */}
        <div className="border-t border-gray-100 dark:border-industrial-border p-5 flex flex-col gap-2.5">
          <button
            onClick={onClose}
            className="w-full rounded-lg bg-industrial-accent py-2.5 text-sm font-bold text-black shadow-sm hover:bg-industrial-accent-hover active:scale-95 transition-all duration-150"
          >
            Mark as Resolved
          </button>
          <button
            onClick={onClose}
            className="w-full rounded-lg border border-gray-200 dark:border-industrial-border py-2.5 text-sm font-medium text-gray-600 dark:text-industrial-muted hover:border-gray-300 hover:bg-gray-50 dark:hover:bg-industrial-nav-hover transition-colors"
          >
            Ignore
          </button>
        </div>
      </div>
    </>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────

function NoAnalysisFound() {
  return (
    <div className="flex flex-col items-center justify-center gap-5 rounded-xl border border-dashed border-gray-200 dark:border-industrial-border bg-white dark:bg-industrial-surface py-24 text-center transition-colors duration-200">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gray-100 dark:bg-industrial-surface-2">
        <ScanSearch className="h-8 w-8 text-gray-400 dark:text-industrial-muted" />
      </div>
      <div>
        <p className="text-base font-semibold text-gray-900 dark:text-industrial-text">
          No Analysis Found
        </p>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted max-w-xs mx-auto">
          Run a clash detection analysis on a blueprint first, then come back here to review the results.
        </p>
      </div>
      <Link
        href="/upload"
        className="flex items-center gap-2 rounded-lg bg-industrial-accent px-5 py-2.5 text-sm font-bold text-black shadow-sm hover:bg-industrial-accent-hover active:scale-95 transition-all duration-150"
      >
        <UploadCloud className="h-4 w-4" />
        Go to Plan Upload
      </Link>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function ClashDetectionPage() {
  const [analysis, setAnalysis] = useState<StoredAnalysis | null>(null);
  const [ready, setReady] = useState(false);
  const [selectedIssue, setSelectedIssue] = useState<ClashItem | null>(null);
  const [aiRecommendation, setAiRecommendation] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [hoveredIssueId, setHoveredIssueId] = useState<string | null>(null);

  // ── Load from localStorage on mount ───────────────────────────────────
  useEffect(() => {
    try {
      const raw = localStorage.getItem('latest_analysis');
      if (raw) {
        const parsed: StoredAnalysis = JSON.parse(raw);
        setAnalysis(parsed);
      }
    } catch {
      // Corrupt data — treat as missing
    }
    setReady(true);
  }, []);

  // ── AI recommendation ──────────────────────────────────────────────────
  const fetchAIRecommendation = useCallback(async (issue: ClashItem) => {
    setIsGenerating(true);
    setAiRecommendation(null);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/generate-recommendation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          className: issue.elements,
          x: issue.x,
          y: issue.y,
          severity: issue.severity,
        }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data: { recommendation: string } = await res.json();
      setAiRecommendation(data.recommendation ?? null);
    } catch {
      setAiRecommendation('Unable to generate recommendation. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  }, []);

  const handleSelectIssue = useCallback(
    (item: ClashItem) => {
      setSelectedIssue(item);
      setAiRecommendation(null);
      fetchAIRecommendation(item);
    },
    [fetchAIRecommendation],
  );

  const handleCloseDrawer = useCallback(() => {
    setSelectedIssue(null);
    setAiRecommendation(null);
  }, []);

  // ── PDF export ─────────────────────────────────────────────────────────
  const generatePDFReport = useCallback(() => {
    if (!analysis) return;
    const doc = new jsPDF();
    const generatedAt = new Date().toLocaleString();

    doc.setFontSize(20);
    doc.setFont('helvetica', 'bold');
    doc.text('ConstructAI — Clash Detection Report', 14, 22);
    doc.setDrawColor(230, 100, 20);
    doc.setLineWidth(0.8);
    doc.line(14, 26, 196, 26);

    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(100);
    doc.text(`File: ${analysis.filename ?? 'N/A'}`, 14, 33);
    doc.text(`Generated: ${generatedAt}`, 14, 39);
    doc.text(`Total Detections: ${analysis.total_detections}`, 14, 45);
    doc.setTextColor(0);

    const rows = analysis.detections.map((d, i) => [
      `DET-${String(i + 1).padStart(3, '0')}`,
      d.class_name.replace(/_/g, ' '),
      `${(d.confidence <= 1 ? d.confidence * 100 : d.confidence).toFixed(1)}%`,
      `x:${Math.round(d.bbox.x_min)}, y:${Math.round(d.bbox.y_min)}, w:${Math.round(d.bbox.x_max - d.bbox.x_min)}, h:${Math.round(d.bbox.y_max - d.bbox.y_min)}`,
    ]);

    autoTable(doc, {
      startY: 52,
      head: [['Issue ID', 'Detected Class', 'Confidence (%)', 'Coordinates (x, y, w, h)']],
      body: rows,
      headStyles: { fillColor: [230, 100, 20], textColor: 255, fontStyle: 'bold', fontSize: 9 },
      bodyStyles: { fontSize: 9, cellPadding: 4 },
      alternateRowStyles: { fillColor: [248, 248, 248] },
      columnStyles: { 0: { cellWidth: 24 }, 2: { halign: 'center', cellWidth: 32 } },
    });

    const pageCount = (
      doc as jsPDF & { internal: { getNumberOfPages: () => number } }
    ).internal.getNumberOfPages();
    for (let p = 1; p <= pageCount; p++) {
      doc.setPage(p);
      doc.setFontSize(8);
      doc.setTextColor(160);
      doc.text(
        `ConstructAI • Confidential • Page ${p} of ${pageCount}`,
        14,
        doc.internal.pageSize.getHeight() - 8,
      );
    }
    doc.save('ConstructAI_Clash_Report.pdf');
  }, [analysis]);

  // ── Derived data ───────────────────────────────────────────────────────
  const blueprintUrl =
    analysis?.blueprintUrl ??
    'https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/Bikeplan.svg/1200px-Bikeplan.svg.png';

  const derivedBoxes: BoundingBox[] = (analysis?.detections ?? []).map((d, i) => ({
    id:       `DET-${String(i + 1).padStart(3, '0')}`,
    top:      (d.bbox.y_min / 1000) * 100,   // fallback scaling; real dims stored if image was loaded
    left:     (d.bbox.x_min / 1000) * 100,
    width:    ((d.bbox.x_max - d.bbox.x_min) / 1000) * 100,
    height:   ((d.bbox.y_max - d.bbox.y_min) / 1000) * 100,
    label:    `${d.class_name} ${(d.confidence * 100).toFixed(0)}%`,
    severity: toSeverity(d.confidence),
  }));

  const derivedClashes: ClashItem[] = (analysis?.detections ?? []).map((d, i) => ({
    id:        `DET-${String(i + 1).padStart(3, '0')}`,
    elements:  d.class_name,
    severity:  toSeverity(d.confidence),
    location:  `x: ${Math.round(d.bbox.x_min)}, y: ${Math.round(d.bbox.y_min)}`,
    x:         Math.round(d.bbox.x_min),
    y:         Math.round(d.bbox.y_min),
    imgWidth:  analysis?.imageWidth  ?? 1000,
    imgHeight: analysis?.imageHeight ?? 1000,
  }));

  const highCount = derivedClashes.filter((c) => c.severity === 'High').length;
  const medCount  = derivedClashes.filter((c) => c.severity === 'Medium').length;
  const lowCount  = derivedClashes.filter((c) => c.severity === 'Low').length;

  // ── Hydration guard ────────────────────────────────────────────────────
  if (!ready) {
    return (
      <div className="flex items-center justify-center py-32">
        <span className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-industrial-accent" />
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6 max-w-350 mx-auto">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-industrial-text">
            Clash Detection
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
            Review AI-identified structural conflicts from your latest blueprint analysis.
          </p>
        </div>
        {analysis && (
          <div className="flex items-center gap-2">
            <button
              onClick={generatePDFReport}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-industrial-border px-3 py-2 text-xs font-semibold text-gray-600 dark:text-industrial-muted hover:border-industrial-accent hover:bg-orange-50 hover:text-industrial-accent dark:hover:border-industrial-accent dark:hover:bg-industrial-accent-subtle dark:hover:text-industrial-accent transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
              Download Report
            </button>
            <Link
              href="/upload"
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-industrial-border px-3 py-2 text-xs font-semibold text-gray-600 dark:text-industrial-muted hover:border-gray-300 hover:bg-gray-50 dark:hover:bg-industrial-nav-hover transition-colors"
            >
              <UploadCloud className="h-3.5 w-3.5" />
              New Analysis
            </Link>
          </div>
        )}
      </div>

      {/* ── No data state ── */}
      {!analysis && <NoAnalysisFound />}

      {/* ── Results ── */}
      {analysis && (
        <>
          {/* Summary bar */}
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 dark:border-industrial-border bg-white dark:bg-industrial-surface px-5 py-3 transition-colors duration-200">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-industrial-accent">
                <ScanSearch className="h-3.5 w-3.5 text-black" />
              </span>
              <span className="text-sm font-semibold text-gray-900 dark:text-industrial-text">
                Analysis Complete
              </span>
            </div>
            <div className="flex gap-2 flex-wrap">
              <span className="rounded-full bg-red-100 dark:bg-red-500/20 px-2.5 py-0.5 text-xs font-semibold text-red-700 dark:text-red-400">
                {highCount} High
              </span>
              <span className="rounded-full bg-yellow-100 dark:bg-yellow-400/20 px-2.5 py-0.5 text-xs font-semibold text-yellow-800 dark:text-yellow-300">
                {medCount} Medium
              </span>
              <span className="rounded-full bg-blue-100 dark:bg-blue-500/20 px-2.5 py-0.5 text-xs font-semibold text-blue-700 dark:text-blue-400">
                {lowCount} Low
              </span>
            </div>
            <p className="ml-auto text-xs text-gray-400 dark:text-industrial-muted truncate">
              {analysis.filename}
            </p>
          </div>

          {/* Split-pane grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

            {/* Left: Annotated Blueprint (sticky) */}
            <div className="lg:col-span-8 sticky top-6">
              <div className="rounded-xl border border-gray-100 dark:border-industrial-border bg-white dark:bg-industrial-surface shadow-sm dark:shadow-none overflow-hidden transition-colors duration-200">
                <div className="border-b border-gray-100 dark:border-industrial-border px-5 py-3">
                  <h2 className="text-sm font-semibold text-gray-900 dark:text-industrial-text">
                    Blueprint — Clash Overlay
                  </h2>
                  <p className="text-xs text-gray-400 dark:text-industrial-muted mt-0.5">
                    Bounding boxes highlight detected conflict zones
                  </p>
                </div>
                <div className="p-4">
                  <AnnotatedBlueprint blueprintUrl={blueprintUrl} boxes={derivedBoxes} hoveredIssueId={hoveredIssueId} />
                </div>
                {/* Legend */}
                <div className="flex flex-wrap gap-4 border-t border-gray-100 dark:border-industrial-border px-5 py-3">
                  {(['High', 'Medium', 'Low'] as Severity[]).map((s) => (
                    <span
                      key={s}
                      className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-industrial-muted"
                    >
                      <span className={`h-3 w-5 rounded-sm border-2 ${SEVERITY_BOX[s]}`} />
                      {s} severity
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Right: Compact Issues List (scrollable) */}
            <div className="lg:col-span-4">
              <div className="rounded-xl border border-gray-100 dark:border-industrial-border bg-white dark:bg-industrial-surface shadow-sm dark:shadow-none overflow-hidden transition-colors duration-200">
                <div className="border-b border-gray-100 dark:border-industrial-border px-4 py-3">
                  <h2 className="text-sm font-semibold text-gray-900 dark:text-industrial-text">
                    Detected Issues
                  </h2>
                  <p className="text-xs text-gray-400 dark:text-industrial-muted mt-0.5">
                    {derivedClashes.length} issue
                    {derivedClashes.length !== 1 ? 's' : ''} found — click to inspect
                  </p>
                </div>
                <div className="max-h-[calc(100vh-220px)] overflow-y-auto p-3 custom-scrollbar">
                  <ClashList clashes={derivedClashes} onSelect={handleSelectIssue} onHover={setHoveredIssueId} />
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Issue drawer */}
      <IssueDrawer
        issue={selectedIssue}
        onClose={handleCloseDrawer}
        aiRecommendation={aiRecommendation}
        isGenerating={isGenerating}
      />
    </div>
  );
}
