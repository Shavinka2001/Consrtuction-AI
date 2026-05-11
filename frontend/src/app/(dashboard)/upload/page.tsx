'use client';

import { useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import api, { type ApiError } from '@/lib/api';
import {
  UploadCloud,
  FileImage,
  X,
  ScanSearch,
  AlertTriangle,
  Zap,
  RotateCcw,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────────────────

interface UploadedFile {
  name: string;
  size: number;
  previewUrl: string;
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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

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

// ── IssueDrawer removed — results rendered on /clash-detection ───────────────────────────────

// ── Page ───────────────────────────────────────────────────────────────────

export default function UploadPage() {
  const router = useRouter();
  const [uploadedFile, setUploadedFile] = useState<UploadedFile | null>(null);
  // Raw File object kept separately so FormData can read its bytes.
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((file: File) => {
    setAnalysisError(null);
    setSelectedFile(file);
    const isImage = file.type.startsWith('image/');
    const previewUrl = isImage ? URL.createObjectURL(file) : PLACEHOLDER_BLUEPRINT;
    setUploadedFile({ name: file.name, size: file.size, previewUrl });
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

  const handleAnalyzeImage = async () => {
    if (!selectedFile) {
      setAnalysisError('Please select an image before running analysis.');
      return;
    }

    setIsAnalyzing(true);
    setAnalysisError(null);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const { data } = await api.post<AnalysisResponse>('/analyze-site', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      // Capture natural image dimensions so clash-detection can compute accurate percentages
      let imageWidth: number | undefined;
      let imageHeight: number | undefined;
      const previewUrl = uploadedFile?.previewUrl;
      if (previewUrl && selectedFile.type.startsWith('image/')) {
        await new Promise<void>((resolve) => {
          const img = new window.Image();
          img.onload  = () => { imageWidth = img.naturalWidth; imageHeight = img.naturalHeight; resolve(); };
          img.onerror = () => resolve();
          img.src = previewUrl;
        });
      }

      localStorage.setItem(
        'latest_analysis',
        JSON.stringify({
          ...data,
          blueprintUrl: previewUrl ?? null,
          imageWidth,
          imageHeight,
        }),
      );
      router.push('/clash-detection');
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
    setIsAnalyzing(false);
    setAnalysisError(null);
  };


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
        {uploadedFile && (
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
      {!uploadedFile && (
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
      {uploadedFile && !isAnalyzing && (
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
    </div>
  );
}

