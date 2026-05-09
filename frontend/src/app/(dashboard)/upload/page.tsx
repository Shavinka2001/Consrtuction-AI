'use client';

import { useState, useRef, useCallback } from 'react';
import Image from 'next/image';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import api, { type ApiError } from '@/lib/api';
import {
  UploadCloud,
  FileImage,
  X,
  ScanSearch,
  AlertTriangle,
  AlertCircle,
  Zap,
  ArrowUpRight,
  RotateCcw,
  Download,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────

interface UploadedFile {
  name: string;
  size: number;
  previewUrl: string;
}

type Severity = 'High' | 'Medium' | 'Low';

interface BoundingBox {
  /** All values are percentages of the container (0-100) */
  top: number;
  left: number;
  width: number;
  height: number;
  label: string;
  severity: Severity;
}

interface ClashItem {
  id: string;
  label: string;
  elements: string;
  severity: Severity;
  location: string;
}

/** Mirrors the DetectionSchema returned by POST /api/analyze-site */
interface AnalysisDetection {
  class_name: string;
  confidence: number;
  bbox: { x_min: number; y_min: number; x_max: number; y_max: number };
}

/** Mirrors the AnalyzeSiteResponse returned by POST /api/analyze-site */
interface AnalysisResponse {
  success: boolean;
  filename: string;
  detections: AnalysisDetection[];
  total_detections: number;
}

// ── Constants ─────────────────────────────────────────────────────────────

const PLACEHOLDER_BLUEPRINT =
  'https://upload.wikimedia.org/wikipedia/commons/thumb/3/3f/Bikeplan.svg/1200px-Bikeplan.svg.png';

// ── Helpers ────────────────────────────────────────────────────────────────

/** Maps a YOLO confidence score to a UI severity tier. */
function toSeverity(confidence: number): Severity {
  if (confidence >= 0.7) return 'High';
  if (confidence >= 0.4) return 'Medium';
  return 'Low';
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const SEVERITY_BOX: Record<Severity, string> = {
  High: 'border-red-500 bg-red-500/10',
  Medium: 'border-yellow-400 bg-yellow-400/10',
  Low: 'border-blue-400 bg-blue-400/10',
};

const SEVERITY_LABEL: Record<Severity, string> = {
  High: 'bg-red-500 text-white',
  Medium: 'bg-yellow-400 text-black',
  Low: 'bg-blue-400 text-white',
};

const SEVERITY_BADGE: Record<Severity, string> = {
  High: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',
  Medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-400/20 dark:text-yellow-300',
  Low: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
};

const SEVERITY_ICON: Record<Severity, string> = {
  High: 'text-red-500',
  Medium: 'text-yellow-400',
  Low: 'text-blue-400',
};

// ── Sub-components ─────────────────────────────────────────────────────────

function DropZone({
  isDragging,
  fileInputRef,
  onDrop,
  onDragOver,
  onDragLeave,
  onInputChange,
}: {
  isDragging: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragLeave: (e: React.DragEvent<HTMLDivElement>) => void;
  onInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload file drop zone"
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onClick={() => fileInputRef.current?.click()}
      onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
      className={`relative flex flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed px-6 py-16 text-center cursor-pointer transition-colors duration-150 outline-none focus-visible:ring-2 focus-visible:ring-industrial-accent focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-industrial-bg
        ${
          isDragging
            ? 'border-industrial-accent bg-orange-50 dark:bg-industrial-accent-subtle'
            : 'border-gray-300 bg-white hover:border-industrial-accent hover:bg-orange-50/50 dark:border-industrial-border dark:bg-industrial-surface dark:hover:border-industrial-accent dark:hover:bg-industrial-accent-subtle/60'
        }`}
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-orange-100 dark:bg-industrial-accent-subtle">
        <UploadCloud
          className={`h-8 w-8 transition-colors ${
            isDragging ? 'text-industrial-accent' : 'text-gray-400 dark:text-industrial-muted'
          }`}
        />
      </div>
      <div>
        <p className="text-base font-semibold text-gray-700 dark:text-industrial-text">
          {isDragging ? 'Drop your file here' : 'Drag & drop your blueprint'}
        </p>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
          or{' '}
          <span className="font-medium text-industrial-accent underline underline-offset-2">
            browse files
          </span>
        </p>
      </div>
      <p className="text-xs text-gray-400 dark:text-industrial-muted">
        Supports PDF, DWG, DXF, PNG, JPG — up to 50 MB
      </p>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.dwg,.dxf,.png,.jpg,.jpeg,.svg"
        className="sr-only"
        onChange={onInputChange}
        aria-hidden="true"
      />
    </div>
  );
}

function AnalysisLoadingScreen() {
  return (
    <div className="flex flex-col items-center justify-center gap-5 rounded-xl border border-gray-100 bg-white py-24 dark:border-industrial-border dark:bg-industrial-surface transition-colors duration-200">
      <div className="relative flex h-20 w-20 items-center justify-center">
        {/* Outer spinning ring */}
        <span className="absolute inset-0 rounded-full border-4 border-gray-200 dark:border-industrial-border" />
        <span className="absolute inset-0 animate-spin rounded-full border-4 border-transparent border-t-industrial-accent" />
        <ScanSearch className="h-8 w-8 text-industrial-accent" />
      </div>
      <div className="text-center">
        <p className="text-base font-semibold text-gray-900 dark:text-industrial-text">
          Analyzing Blueprints via Construction AI…
        </p>
        <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
          Running clash detection on structural, MEP, and architectural layers
        </p>
      </div>
      {/* Animated progress steps */}
      <ul className="space-y-2 text-left text-sm">
        {[
          'Parsing plan geometry',
          'Cross-referencing MEP layers',
          'Running clash detection engine',
          'Generating bounding box annotations',
        ].map((step, i) => (
          <li
            key={step}
            className="flex items-center gap-2 text-gray-500 dark:text-industrial-muted"
            style={{ animationDelay: `${i * 0.4}s` }}
          >
            <span
              className="h-1.5 w-1.5 animate-pulse rounded-full bg-industrial-accent"
              style={{ animationDelay: `${i * 0.3}s` }}
            />
            {step}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ClashBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${SEVERITY_BADGE[severity]}`}
    >
      {severity}
    </span>
  );
}

function AnnotatedBlueprint({
  file,
  boxes,
}: {
  file: UploadedFile;
  boxes: BoundingBox[];
}) {
  return (
    <div className="relative w-full overflow-hidden rounded-lg bg-gray-100 dark:bg-industrial-surface-2" style={{ aspectRatio: '4/3' }}>
      <Image
        src={file.previewUrl}
        alt="Annotated blueprint"
        fill
        className="object-contain p-2"
        unoptimized={file.previewUrl.startsWith('blob:')}
      />
      {/* Bounding box overlays */}
      {boxes.map((box, index) => (
        <div
          key={`${box.label}-${index}`}
          className={`absolute rounded border-2 ${SEVERITY_BOX[box.severity]}`}
          style={{
            top: `${box.top}%`,
            left: `${box.left}%`,
            width: `${box.width}%`,
            height: `${box.height}%`,
          }}
        >
          <span
            className={`absolute -top-5 left-0 whitespace-nowrap rounded-t px-1.5 py-0.5 text-[10px] font-bold leading-tight ${SEVERITY_LABEL[box.severity]}`}
          >
            {box.label}
          </span>
        </div>
      ))}
    </div>
  );
}

function ClashList({ clashes, onSelect }: { clashes: ClashItem[]; onSelect: (item: ClashItem) => void }) {
  return (
    <ul className="space-y-3">
      {clashes.map((clash) => (
        <li
          key={clash.id}
          className="rounded-lg border border-gray-100 bg-gray-50 p-4 dark:border-industrial-border dark:bg-industrial-surface-2 transition-colors duration-150"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <AlertTriangle className={`h-4 w-4 shrink-0 ${SEVERITY_ICON[clash.severity]}`} />
              <span className="text-xs font-mono font-semibold text-gray-400 dark:text-industrial-muted">
                {clash.id}
              </span>
            </div>
            <ClashBadge severity={clash.severity} />
          </div>

          <p className="mt-2 text-sm font-semibold text-gray-900 dark:text-industrial-text">
            {clash.elements}
          </p>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-industrial-muted">
            {clash.location}
          </p>

          <button
            onClick={() => onSelect(clash)}
            className="mt-3 flex items-center gap-1 rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-industrial-accent hover:text-industrial-accent dark:border-industrial-border dark:text-industrial-muted dark:hover:border-industrial-accent dark:hover:text-industrial-accent transition-colors"
          >
            View Details
            <ArrowUpRight className="h-3 w-3" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function ConfidenceCards({ detections }: { detections: AnalysisDetection[] }) {
  function getColors(confidence: number) {
    const pct = confidence <= 1 ? confidence * 100 : confidence;
    if (pct >= 80)
      return {
        bar: 'bg-emerald-500',
        text: 'text-emerald-600 dark:text-emerald-400',
        iconBg: 'bg-emerald-50 dark:bg-emerald-500/10',
      };
    if (pct >= 50)
      return {
        bar: 'bg-amber-500',
        text: 'text-amber-600 dark:text-amber-400',
        iconBg: 'bg-amber-50 dark:bg-amber-500/10',
      };
    return {
      bar: 'bg-rose-500',
      text: 'text-rose-600 dark:text-rose-400',
      iconBg: 'bg-rose-50 dark:bg-rose-500/10',
    };
  }

  if (detections.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-400 dark:text-industrial-muted">
        No detections found.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {detections.map((item, index) => {
        const pct = item.confidence <= 1 ? item.confidence * 100 : item.confidence;
        const colors = getColors(item.confidence);
        const displayName =
          item.class_name.charAt(0).toUpperCase() +
          item.class_name.slice(1).replace(/_/g, ' ');

        return (
          <div
            key={`${item.class_name}-${index}`}
            className="bg-white border border-gray-100 rounded-xl shadow-sm p-4 hover:shadow-md transition-shadow dark:bg-industrial-surface dark:border-industrial-border"
          >
            {/* Top row: icon + name */}
            <div className="flex items-center gap-2.5 mb-3">
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${colors.iconBg}`}
              >
                <AlertCircle className={`h-4 w-4 ${colors.text}`} />
              </div>
              <span className="text-sm font-bold leading-tight text-gray-900 dark:text-industrial-text line-clamp-1">
                {displayName}
              </span>
            </div>

            {/* Thin progress bar */}
            <div className="w-full rounded-full bg-gray-100 dark:bg-industrial-surface-2 h-1.5 mb-2">
              <div
                className={`h-1.5 rounded-full transition-all duration-700 ${colors.bar}`}
                style={{ width: `${Math.min(pct, 100).toFixed(1)}%` }}
              />
            </div>

            {/* Bottom row: label + percentage */}
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400 dark:text-industrial-muted">Confidence</span>
              <span className={`text-xs font-semibold tabular-nums ${colors.text}`}>
                {pct.toFixed(1)}%
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── IssueDrawer ────────────────────────────────────────────────────────────

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
  const [assignee, setAssignee] = useState<string>('');

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
        className="fixed inset-y-0 right-0 w-full md:w-1/3 bg-white shadow-2xl z-50 transform transition-transform flex flex-col"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-gray-100 px-5 py-4">
          <div className="min-w-0">
            <p className="text-[10px] font-mono font-semibold text-gray-400 mb-0.5">{issue.id}</p>
            <h2 className="text-base font-bold text-gray-900 leading-snug">
              {issue.elements.charAt(0).toUpperCase() + issue.elements.slice(1).replace(/_/g, ' ')}
            </h2>
            <span
              className={`inline-flex items-center gap-1 mt-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${SEVERITY_BADGE[issue.severity]}`}
            >
              {issue.severity} Severity
            </span>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors"
            aria-label="Close drawer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Section 1: Location Details */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Location Details
            </h3>
            <div className="rounded-lg border border-gray-100 bg-gray-50 p-3 space-y-2">
              {issue.location.split(',').map((part, i) => {
                const colonIdx = part.indexOf(':');
                const key = colonIdx !== -1 ? part.slice(0, colonIdx).trim() : part.trim();
                const val = colonIdx !== -1 ? part.slice(colonIdx + 1).trim() : '—';
                return (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                      {key}
                    </span>
                    <span className="font-mono text-sm font-bold text-gray-900">{val} px</span>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Section 2: AI Recommendation */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
              AI Recommendation
            </h3>
            <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-3.5">
              {isGenerating ? (
                <div className="flex items-start gap-2.5">
                  <div className="mt-0.5 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-500" />
                  <div className="flex-1 space-y-2">
                    <p className="text-xs font-medium text-indigo-500 animate-pulse">
                      AI is analyzing structural context…
                    </p>
                    <div className="h-2.5 w-full animate-pulse rounded bg-indigo-100" />
                    <div className="h-2.5 w-4/5 animate-pulse rounded bg-indigo-100" />
                    <div className="h-2.5 w-3/5 animate-pulse rounded bg-indigo-100" />
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  <Zap className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
                  <p className="text-sm text-indigo-800 leading-relaxed">
                    <span className="font-semibold">AI Suggestion:</span>{' '}
                    {aiRecommendation ?? 'Click \'View Details\' to generate a recommendation.'}
                  </p>
                </div>
              )}
            </div>
          </section>

          {/* Section 3: Assignee */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
              Assignee
            </h3>
            <select
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-industrial-accent focus:outline-none focus:ring-1 focus:ring-industrial-accent"
            >
              <option value="">— Select Assignee —</option>
              <option value="site-engineer">Site Engineer</option>
              <option value="architect">Architect</option>
            </select>
          </section>
        </div>

        {/* Footer */}
        <div className="border-t border-gray-100 p-5 flex flex-col gap-2.5">
          <button
            onClick={onClose}
            className="w-full rounded-lg bg-industrial-accent py-2.5 text-sm font-bold text-black shadow-sm hover:bg-industrial-accent-hover active:scale-95 transition-all duration-150"
          >
            Mark as Resolved
          </button>
          <button
            onClick={onClose}
            className="w-full rounded-lg border border-gray-200 py-2.5 text-sm font-medium text-gray-600 hover:border-gray-300 hover:bg-gray-50 transition-colors"
          >
            Ignore
          </button>
        </div>
      </div>
    </>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function UploadPage() {
  const [uploadedFile, setUploadedFile] = useState<UploadedFile | null>(null);
  const [selectedIssue, setSelectedIssue] = useState<ClashItem | null>(null);
  const [aiRecommendation, setAiRecommendation] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  // Raw File object kept separately so FormData can read its bytes.
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  // Natural pixel dimensions of the uploaded image — used for bbox conversion.
  const [imageDimensions, setImageDimensions] = useState<{ width: number; height: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const [analysisResults, setAnalysisResults] = useState<AnalysisResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((file: File) => {
    setAnalysisComplete(false);
    setAnalysisResults(null);
    setAnalysisError(null);
    setSelectedFile(file);
    const isImage = file.type.startsWith('image/');
    const previewUrl = isImage ? URL.createObjectURL(file) : PLACEHOLDER_BLUEPRINT;
    setUploadedFile({ name: file.name, size: file.size, previewUrl });
    // Capture natural dimensions so bbox pixel coords can be converted to %.
    if (isImage) {
      const img = new window.Image();
      img.onload = () =>
        setImageDimensions({ width: img.naturalWidth, height: img.naturalHeight });
      img.src = previewUrl;
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = '';
  };

  const fetchAIRecommendation = useCallback(async (issue: ClashItem) => {
    const parts = issue.location.split(',');
    const x = parseFloat(parts[0]?.split(':')[1] ?? '0');
    const y = parseFloat(parts[1]?.split(':')[1] ?? '0');
    setIsGenerating(true);
    setAiRecommendation(null);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/generate-recommendation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ className: issue.elements, x, y, severity: issue.severity }),
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

  const handleAnalyzeImage = async () => {
    if (!selectedFile) {
      setAnalysisError('Please select an image before running analysis.');
      return;
    }

    setIsAnalyzing(true);
    setAnalysisComplete(false);
    setAnalysisResults(null);
    setAnalysisError(null);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const { data } = await api.post<AnalysisResponse>('/analyze-site', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setAnalysisResults(data);
      setAnalysisComplete(true);
    } catch (err) {
      const message =
        (err as ApiError).friendlyMessage ??
        (err instanceof Error ? err.message : 'Analysis failed. Please try again.');
      setAnalysisError(message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleReset = () => {
    setUploadedFile(null);
    setSelectedFile(null);
    setImageDimensions(null);
    setIsAnalyzing(false);
    setAnalysisComplete(false);
    setAnalysisResults(null);
    setAnalysisError(null);
    setSelectedIssue(null);
    setAiRecommendation(null);
  };

  const generatePDFReport = () => {
    if (!analysisResults) return;

    const doc = new jsPDF();
    const generatedAt = new Date().toLocaleString();

    // ── Header ──────────────────────────────────────────────────────────────
    doc.setFontSize(20);
    doc.setFont('helvetica', 'bold');
    doc.text('ConstructAI — Clash Detection Report', 14, 22);

    doc.setDrawColor(230, 100, 20);
    doc.setLineWidth(0.8);
    doc.line(14, 26, 196, 26);

    // ── Metadata ─────────────────────────────────────────────────────────────
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(100);
    doc.text(`File: ${uploadedFile?.name ?? 'N/A'}`, 14, 33);
    doc.text(`Generated: ${generatedAt}`, 14, 39);
    doc.text(
      `Total Detections: ${analysisResults.total_detections}  | High: ${highCount}  | Medium: ${medCount}  | Low: ${lowCount}`,
      14,
      45,
    );
    doc.setTextColor(0);

    // ── Table ─────────────────────────────────────────────────────────────────
    const rows = analysisResults.detections.map((d, i) => [
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

    // ── Footer ────────────────────────────────────────────────────────────────
    const pageCount = (doc as jsPDF & { internal: { getNumberOfPages: () => number } }).internal.getNumberOfPages();
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
  };

  // ── Derived results (converted from backend response) ──────────────────

  const derivedBoxes: BoundingBox[] = (() => {
    if (!analysisResults || !imageDimensions) return [];
    return analysisResults.detections.map((d) => ({
      top: (d.bbox.y_min / imageDimensions.height) * 100,
      left: (d.bbox.x_min / imageDimensions.width) * 100,
      width: ((d.bbox.x_max - d.bbox.x_min) / imageDimensions.width) * 100,
      height: ((d.bbox.y_max - d.bbox.y_min) / imageDimensions.height) * 100,
      label: `${d.class_name} ${(d.confidence * 100).toFixed(0)}%`,
      severity: toSeverity(d.confidence),
    }));
  })();

  const derivedClashes: ClashItem[] = (analysisResults?.detections ?? []).map((d, i) => ({
    id: `DET-${String(i + 1).padStart(3, '0')}`,
    label: d.class_name,
    elements: d.class_name,
    severity: toSeverity(d.confidence),
    location: `x: ${Math.round(d.bbox.x_min)}, y: ${Math.round(d.bbox.y_min)}`,
  }));

  const highCount = derivedClashes.filter((c) => c.severity === 'High').length;
  const medCount  = derivedClashes.filter((c) => c.severity === 'Medium').length;
  const lowCount  = derivedClashes.filter((c) => c.severity === 'Low').length;

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-industrial-text">
            Plan Upload
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-industrial-muted">
            Upload your construction blueprints or CAD exports. Our AI will scan
            them for clashes and structural conflicts.
          </p>
        </div>
        {(uploadedFile || analysisComplete) && (
          <button
            onClick={handleReset}
            className="flex shrink-0 items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 hover:border-gray-300 hover:bg-gray-50 dark:border-industrial-border dark:text-industrial-muted dark:hover:border-industrial-muted dark:hover:bg-industrial-nav-hover transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Upload new plan
          </button>
        )}
      </div>

      {/* ── Error banner ── */}
      {analysisError && (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-400"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{analysisError}</span>
          <button
            onClick={() => setAnalysisError(null)}
            className="ml-auto shrink-0 rounded p-0.5 hover:bg-red-100 dark:hover:bg-red-500/20"
            aria-label="Dismiss error"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* ── State: no file ── */}
      {!uploadedFile && !analysisComplete && (
        <DropZone
          isDragging={isDragging}
          fileInputRef={fileInputRef}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onInputChange={handleInputChange}
        />
      )}

      {/* ── State: file loaded, not yet analysed ── */}
      {uploadedFile && !isAnalyzing && !analysisComplete && (
        <div className="rounded-xl border border-gray-100 bg-white shadow-sm dark:border-industrial-border dark:bg-industrial-surface dark:shadow-none transition-colors duration-200 overflow-hidden">
          {/* Meta bar */}
          <div className="flex items-center justify-between gap-3 border-b border-gray-100 dark:border-industrial-border px-5 py-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <FileImage className="h-5 w-5 shrink-0 text-industrial-accent" />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-gray-900 dark:text-industrial-text">
                  {uploadedFile.name}
                </p>
                <p className="text-xs text-gray-400 dark:text-industrial-muted">
                  {formatBytes(uploadedFile.size)}
                </p>
              </div>
            </div>
            <button
              onClick={handleReset}
              className="shrink-0 rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-industrial-nav-hover dark:hover:text-industrial-text transition-colors"
              aria-label="Remove file"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Blueprint preview */}
          <div className="relative w-full bg-gray-100 dark:bg-industrial-surface-2" style={{ aspectRatio: '16/9' }}>
            <Image
              src={uploadedFile.previewUrl}
              alt="Uploaded blueprint preview"
              fill
              className="object-contain p-4"
              unoptimized={uploadedFile.previewUrl.startsWith('blob:')}
            />
          </div>

          {/* Action bar */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 px-5 py-4">
            <p className="text-sm text-gray-500 dark:text-industrial-muted">
              Plan loaded. Run the AI engine to detect clashes and overlaps.
            </p>
            <button
              onClick={handleAnalyzeImage}
              disabled={isAnalyzing}
              className="flex shrink-0 items-center gap-2 rounded-lg bg-industrial-accent px-5 py-2.5 text-sm font-bold text-black shadow-sm hover:bg-industrial-accent-hover active:scale-95 transition-all duration-150 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <Zap className="h-4 w-4" />
              Run AI Clash Detection
            </button>
          </div>
        </div>
      )}

      {/* ── State: loading ── */}
      {isAnalyzing && <AnalysisLoadingScreen />}

      {/* ── State: results ── */}
      {analysisComplete && uploadedFile && (
        <>
          {/* Summary bar */}
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 bg-white px-5 py-3 dark:border-industrial-border dark:bg-industrial-surface transition-colors duration-200">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-industrial-accent">
                <ScanSearch className="h-3.5 w-3.5 text-black" />
              </span>
              <span className="text-sm font-semibold text-gray-900 dark:text-industrial-text">
                Analysis Complete
              </span>
            </div>
            <div className="flex gap-2 flex-wrap">
              <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700 dark:bg-red-500/20 dark:text-red-400">
                {highCount} High
              </span>
              <span className="rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-semibold text-yellow-800 dark:bg-yellow-400/20 dark:text-yellow-300">
                {medCount} Medium
              </span>
              <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700 dark:bg-blue-500/20 dark:text-blue-400">
                {lowCount} Low
              </span>
            </div>
            <div className="ml-auto flex items-center gap-3">
              <button
                onClick={generatePDFReport}
                className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:border-industrial-accent hover:bg-orange-50 hover:text-industrial-accent dark:border-industrial-border dark:text-industrial-muted dark:hover:border-industrial-accent dark:hover:bg-industrial-accent-subtle dark:hover:text-industrial-accent transition-colors"
              >
                <Download className="h-3.5 w-3.5" />
                Download Report
              </button>
              <p className="text-xs text-gray-400 dark:text-industrial-muted">
                {uploadedFile.name}
              </p>
            </div>
          </div>

          {/* Annotated blueprint — full width */}
          <div className="rounded-xl border border-gray-100 bg-white shadow-sm dark:border-industrial-border dark:bg-industrial-surface dark:shadow-none transition-colors duration-200 overflow-hidden">
            <div className="border-b border-gray-100 dark:border-industrial-border px-5 py-3">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-industrial-text">
                Blueprint — Clash Overlay
              </h2>
              <p className="text-xs text-gray-400 dark:text-industrial-muted mt-0.5">
                Bounding boxes highlight detected conflict zones
              </p>
            </div>
            <div className="p-4">
              <AnnotatedBlueprint file={uploadedFile} boxes={derivedBoxes} />
            </div>
            {/* Legend */}
            <div className="flex flex-wrap gap-4 border-t border-gray-100 dark:border-industrial-border px-5 py-3">
              {(['High', 'Medium', 'Low'] as Severity[]).map((s) => (
                <span key={s} className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-industrial-muted">
                  <span className={`h-3 w-5 rounded-sm border-2 ${SEVERITY_BOX[s]}`} />
                  {s} severity
                </span>
              ))}
            </div>
          </div>

          {/* AI Analysis Results — unified section */}
          <div className="rounded-xl border border-gray-100 bg-white shadow-sm dark:border-industrial-border dark:bg-industrial-surface dark:shadow-none transition-colors duration-200 overflow-hidden">
            {/* Section header */}
            <div className="border-b border-gray-100 dark:border-industrial-border px-5 py-4">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-industrial-text">
                AI Analysis Results
              </h2>
              <p className="text-sm text-gray-500 dark:text-industrial-muted mt-1">
                Review and resolve AI-identified structural conflicts. Click &ldquo;View Details&rdquo; to generate engineering recommendations.
              </p>
            </div>

            {/* Confidence cards */}
            <div className="p-5">
              <ConfidenceCards detections={analysisResults?.detections ?? []} />
            </div>

            {/* Clash issue cards */}
            <div className="border-t border-gray-100 dark:border-industrial-border p-5">
              <ClashList clashes={derivedClashes} onSelect={handleSelectIssue} />
            </div>
          </div>
        </>
      )}

      {/* Issue Resolution Drawer */}
      <IssueDrawer
        issue={selectedIssue}
        onClose={handleCloseDrawer}
        aiRecommendation={aiRecommendation}
        isGenerating={isGenerating}
      />
    </div>
  );
}

