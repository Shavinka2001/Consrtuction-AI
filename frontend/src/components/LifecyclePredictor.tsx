'use client';

import { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Droplets,
  Gauge,
  Loader2,
  ShieldAlert,
  Sparkles,
  Waves,
  Wrench,
} from 'lucide-react';
import api from '@/lib/api';

// â”€â”€ API types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface PredictionRequest {
  Material_Type: number;
  Distance_to_Sea_m: number;
  Humidity_Level: number;
  Maintenance_Cost_Percentage: number;
}

interface PredictionResponse {
  estimated_lifespan_years: number;
  risk_level: 'High' | 'Medium' | 'Low';
  expert_recommendation: string;
  model_confidence: number | null;
  input_echo: PredictionRequest;
}

// â”€â”€ Form state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface FormState {
  Material_Type: string;
  Distance_to_Sea_m: string;
  Humidity_Level: string;
  Maintenance_Cost_Percentage: string;
}

const DEFAULT_FORM: FormState = {
  Material_Type: '0',
  Distance_to_Sea_m: '5000',
  Humidity_Level: '65',
  Maintenance_Cost_Percentage: '2.5',
};

const MATERIAL_LABELS: Record<string, string> = {
  '0': 'Concrete',
  '1': 'Steel',
  '2': 'Timber',
};

// â”€â”€ Helper: risk-level config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const RISK_CONFIG = {
  High: {
    label: 'High Risk',
    bg: 'bg-rose-50 border-rose-200',
    badge: 'bg-rose-100 text-rose-700 border border-rose-200',
    icon: ShieldAlert,
    iconClass: 'text-rose-500',
    bar: 'bg-rose-500',
    textColor: 'text-rose-700',
  },
  Medium: {
    label: 'Medium Risk',
    bg: 'bg-amber-50 border-amber-200',
    badge: 'bg-amber-100 text-amber-700 border border-amber-200',
    icon: AlertTriangle,
    iconClass: 'text-amber-500',
    bar: 'bg-amber-400',
    textColor: 'text-amber-700',
  },
  Low: {
    label: 'Low Risk',
    bg: 'bg-emerald-50 border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
    icon: CheckCircle2,
    iconClass: 'text-emerald-500',
    bar: 'bg-emerald-500',
    textColor: 'text-emerald-700',
  },
};

// â”€â”€ Slider input â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface SliderFieldProps {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  value: string;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (v: string) => void;
}

function SliderField({
  id,
  label,
  description,
  icon: Icon,
  value,
  min,
  max,
  step,
  unit = '',
  onChange,
}: SliderFieldProps) {
  const pct = ((parseFloat(value) - min) / (max - min)) * 100;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label
          htmlFor={id}
          className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 uppercase tracking-wide"
        >
          <Icon className="h-3.5 w-3.5 text-orange-500" />
          {label}
        </label>
        <span className="text-sm font-bold text-gray-900 tabular-nums">
          {value}
          {unit}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer
          bg-gray-200
          [&::-webkit-slider-thumb]:appearance-none
          [&::-webkit-slider-thumb]:h-4
          [&::-webkit-slider-thumb]:w-4
          [&::-webkit-slider-thumb]:rounded-full
          [&::-webkit-slider-thumb]:bg-orange-500
          [&::-webkit-slider-thumb]:shadow-md
          [&::-webkit-slider-thumb]:cursor-pointer
          [&::-moz-range-thumb]:h-4
          [&::-moz-range-thumb]:w-4
          [&::-moz-range-thumb]:rounded-full
          [&::-moz-range-thumb]:bg-orange-500
          [&::-moz-range-thumb]:border-0"
        style={{
          background: `linear-gradient(to right, #f97316 ${pct}%, #e5e7eb ${pct}%)`,
        }}
      />
      <p className="text-[11px] text-gray-400 leading-snug">{description}</p>
    </div>
  );
}

// â”€â”€ Main component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function LifecyclePredictor() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PredictionResponse | null>(null);

  const setField = (key: keyof FormState) => (v: string) =>
    setForm((prev) => ({ ...prev, [key]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const payload: PredictionRequest = {
      Material_Type: parseInt(form.Material_Type, 10),
      Distance_to_Sea_m: parseFloat(form.Distance_to_Sea_m),
      Humidity_Level: parseFloat(form.Humidity_Level),
      Maintenance_Cost_Percentage: parseFloat(form.Maintenance_Cost_Percentage),
    };

    console.log('FINAL prediction payload:', JSON.stringify(payload, null, 2));

    try {
      const response = await api.post<PredictionResponse>(
        '/v1/project/predict-lifecycle',
        payload,
      );
      setResult(response.data);
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { data?: { detail?: string | { msg: string; type: string }[] }; status?: number };
        message?: string;
      };
      const status = axiosErr.response?.status;
      const detail = axiosErr.response?.data?.detail;

      if (status === 503) {
        const backendDetail = typeof detail === 'string' ? detail : null;
        setError(
          backendDetail ??
            'The lifecycle ML model failed to load on the server. ' +
              'Check the uvicorn terminal for the exact error (version mismatch, corrupt .pkl, etc.).',
        );
      } else if (status === 422) {
        if (Array.isArray(detail)) {
          const messages = detail.map((d) => `${d.msg} (${d.type})`).join('; ');
          setError(`Validation error: ${messages}`);
        } else {
          setError(typeof detail === 'string' ? detail : 'Request validation failed. Check all input fields.');
        }
      } else if (typeof detail === 'string') {
        setError(detail);
      } else if (axiosErr.message) {
        setError(`Network error: ${axiosErr.message}`);
      } else {
        setError('An unexpected error occurred. Please check the server logs and try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const risk = result ? RISK_CONFIG[result.risk_level] ?? RISK_CONFIG['Medium'] : null;
  const RiskIcon = risk?.icon ?? ShieldAlert;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
          Lifecycle Degradation Predictor
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Enter structural parameters below. The AI model will estimate the asset&apos;s
          predicted lifespan and generate a Quantity Surveyor maintenance advisory.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-6 items-start">
        {/* â”€â”€ Left sidebar: input form â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        <form
          onSubmit={(e) => handleSubmit(e)}
          className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden"
        >
          {/* Form header */}
          <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-50">
              <Activity className="h-4 w-4 text-orange-500" />
            </span>
            <div>
              <p className="text-sm font-semibold text-gray-900">Input Parameters</p>
              <p className="text-[11px] text-gray-400">4 features â€” matches model training pipeline</p>
            </div>
          </div>

          {/* Fields */}
          <div className="px-5 py-5 space-y-6">
            {/* Material Type */}
            <div className="space-y-1.5">
              <label
                htmlFor="Material_Type"
                className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 uppercase tracking-wide"
              >
                <Wrench className="h-3.5 w-3.5 text-orange-500" />
                Material Type
              </label>
              <select
                id="Material_Type"
                value={form.Material_Type}
                onChange={(e) => setField('Material_Type')(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800
                  focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent cursor-pointer"
              >
                <option value="0">0 â€” Concrete</option>
                <option value="1">1 â€” Steel</option>
                <option value="2">2 â€” Timber</option>
              </select>
              <p className="text-[11px] text-gray-400 leading-snug">
                Primary structural material. Encoded as integer (0, 1, or 2).
              </p>
            </div>

            <div className="border-t border-gray-100" />

            {/* Distance to Sea */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label
                  htmlFor="Distance_to_Sea_m"
                  className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 uppercase tracking-wide"
                >
                  <Waves className="h-3.5 w-3.5 text-orange-500" />
                  Distance to Sea (m)
                </label>
                <span className="text-sm font-bold text-gray-900 tabular-nums">
                  {form.Distance_to_Sea_m} m
                </span>
              </div>
              <input
                id="Distance_to_Sea_m"
                type="number"
                min={0}
                step={1}
                value={form.Distance_to_Sea_m}
                onChange={(e) => setField('Distance_to_Sea_m')(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800
                  focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent"
              />
              <p className="text-[11px] text-gray-400 leading-snug">
                Straight-line distance from the structure to the nearest coastline in metres.
              </p>
            </div>

            <div className="border-t border-gray-100" />

            {/* Humidity Level */}
            <SliderField
              id="Humidity_Level"
              label="Humidity Level (%)"
              description="Average annual relative humidity at the site (0â€“100%). Higher values accelerate corrosion."
              icon={Droplets}
              value={form.Humidity_Level}
              min={0}
              max={100}
              step={1}
              unit="%"
              onChange={setField('Humidity_Level')}
            />

            <div className="border-t border-gray-100" />

            {/* Maintenance Cost Percentage */}
            <SliderField
              id="Maintenance_Cost_Percentage"
              label="Maintenance Cost (%)"
              description="Annual maintenance expenditure as a percentage of the asset replacement value (0â€“100%)."
              icon={Gauge}
              value={form.Maintenance_Cost_Percentage}
              min={0}
              max={100}
              step={0.1}
              unit="%"
              onChange={setField('Maintenance_Cost_Percentage')}
            />
          </div>

          {/* Submit */}
          <div className="px-5 pb-5">
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-orange-500 px-4 py-2.5
                text-sm font-semibold text-white shadow-sm
                hover:bg-orange-600 active:scale-[0.98]
                disabled:opacity-60 disabled:cursor-not-allowed
                transition-all duration-150"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Analysingâ€¦
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Generate Prediction
                </>
              )}
            </button>
          </div>
        </form>

        {/* â”€â”€ Right panel: results â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        <div className="space-y-4">
          {/* Idle / empty state */}
          {!loading && !error && !result && (
            <div className="flex flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed border-gray-200 bg-white py-24 text-center px-6">
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-orange-50">
                <Activity className="h-8 w-8 text-orange-400" />
              </span>
              <div>
                <p className="text-base font-semibold text-gray-700">Results Will Appear Here</p>
                <p className="mt-1 text-sm text-gray-400 max-w-xs">
                  Configure the parameters on the left and click{' '}
                  <span className="font-medium text-orange-500">Generate Prediction</span> to run the
                  ML model.
                </p>
              </div>
            </div>
          )}

          {/* Loading skeleton */}
          {loading && (
            <div className="rounded-xl border border-gray-100 bg-white shadow-sm p-6 space-y-4 animate-pulse">
              <div className="h-5 w-1/3 rounded bg-gray-100" />
              <div className="h-24 rounded-lg bg-gray-100" />
              <div className="h-4 w-2/3 rounded bg-gray-100" />
              <div className="h-4 w-1/2 rounded bg-gray-100" />
              <div className="h-28 rounded-lg bg-gray-100" />
            </div>
          )}

          {/* Error state */}
          {error && !loading && (
            <div className="flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-5">
              <AlertTriangle className="h-5 w-5 text-rose-500 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-rose-700">Prediction failed</p>
                <p className="mt-1 text-sm text-rose-600 leading-relaxed">{error}</p>
              </div>
            </div>
          )}

          {/* Result cards */}
          {result && !loading && risk && (
            <div className="space-y-4">
              {/* Primary result card */}
              <div className={`rounded-xl border ${risk.bg} p-6 space-y-5`}>
                {/* Header row */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <span
                      className={`flex h-12 w-12 items-center justify-center rounded-full border ${risk.badge} shrink-0`}
                    >
                      <RiskIcon className={`h-6 w-6 ${risk.iconClass}`} />
                    </span>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">
                        Degradation Risk
                      </p>
                      <p className={`text-xl font-bold ${risk.textColor}`}>{risk.label}</p>
                    </div>
                  </div>
                  <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${risk.badge}`}>
                    {result.risk_level}
                  </span>
                </div>

                {/* Lifespan metric */}
                <div className="rounded-lg bg-white/70 border border-white px-5 py-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Clock3 className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-gray-600">
                        Estimated Structural Lifespan
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-3xl font-black text-gray-900 tabular-nums">
                        {result.estimated_lifespan_years.toFixed(1)}
                      </span>
                      <span className="ml-1 text-sm font-medium text-gray-500">years</span>
                    </div>
                  </div>

                  {/* Visual bar */}
                  <div className="h-2 w-full rounded-full bg-gray-200 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${risk.bar}`}
                      style={{
                        width: `${Math.min(100, (result.estimated_lifespan_years / 120) * 100).toFixed(1)}%`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-400 font-medium">
                    <span>0 yrs</span>
                    <span className="text-orange-500">30 yrs</span>
                    <span className="text-amber-500">50 yrs</span>
                    <span>120 yrs</span>
                  </div>
                </div>

                {/* Confidence badge */}
                {result.model_confidence !== null && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 font-medium">Model confidence:</span>
                    <span className="rounded-full bg-white/80 border border-gray-200 px-2.5 py-0.5 text-xs font-bold text-gray-700">
                      {(result.model_confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
              </div>

              {/* Expert recommendation card */}
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2.5">
                  <span className="flex h-7 w-7 items-center justify-center rounded-md bg-orange-50">
                    <Wrench className="h-4 w-4 text-orange-500" />
                  </span>
                  <p className="text-sm font-semibold text-gray-900">
                    Quantity Surveyor Recommendation
                  </p>
                </div>
                <div className="px-5 py-4">
                  <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
                    {result.expert_recommendation}
                  </p>
                </div>
              </div>

              {/* Input echo card */}
              <div className="rounded-xl border border-gray-100 bg-gray-50 overflow-hidden">
                <div className="px-5 py-3 border-b border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Input Parameters Used
                  </p>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-gray-100">
                  {[
                    {
                      label: 'Material Type',
                      value: `${result.input_echo.Material_Type} â€” ${MATERIAL_LABELS[String(result.input_echo.Material_Type)] ?? '?'}`,
                      unit: '',
                    },
                    {
                      label: 'Dist. to Sea',
                      value: result.input_echo.Distance_to_Sea_m.toFixed(0),
                      unit: ' m',
                    },
                    {
                      label: 'Humidity',
                      value: result.input_echo.Humidity_Level.toFixed(0),
                      unit: '%',
                    },
                    {
                      label: 'Maint. Cost',
                      value: result.input_echo.Maintenance_Cost_Percentage.toFixed(1),
                      unit: '%',
                    },
                  ].map(({ label, value, unit }) => (
                    <div key={label} className="px-4 py-3 text-center">
                      <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide truncate">
                        {label}
                      </p>
                      <p className="mt-1 text-base font-bold text-gray-800 tabular-nums leading-tight">
                        {value}
                        <span className="text-xs font-normal text-gray-400">{unit}</span>
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Re-run hint */}
              <button
                type="button"
                onClick={() => setResult(null)}
                className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-orange-500 transition-colors"
              >
                <ChevronRight className="h-3.5 w-3.5" />
                Adjust parameters and run again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

