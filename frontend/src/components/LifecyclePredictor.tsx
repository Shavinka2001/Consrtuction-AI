'use client';

import { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Building2,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Droplets,
  FlaskConical,
  Gauge,
  HardHat,
  Home,
  Layers,
  Loader2,
  Paintbrush,
  ShieldAlert,
  Sparkles,
  Wind,
  Wrench,
  Zap,
} from 'lucide-react';
import api from '@/lib/api';

// ── API types ─────────────────────────────────────────────────────────────────

interface PredictionRequest {
  building_type: string;
  foundation_type: string;
  superstructure_type: string;
  roofing_material: string;
  exterior_finish: string;
  hvac_system: string;
  plumbing_system: string;
  electrical_system: string;
  environmental_harshness: number;
  soil_acidity: number;
  maintenance_frequency: number;
  material_quality: number;
}

interface PredictionResponse {
  estimated_lifespan_years: number;
  risk_level: 'High' | 'Medium' | 'Low';
  expert_recommendation: string;
  model_confidence: number | null;
  input_echo: PredictionRequest;
}

// ── Form state ────────────────────────────────────────────────────────────────

interface FormState {
  building_type: string;
  foundation_type: string;
  superstructure_type: string;
  roofing_material: string;
  exterior_finish: string;
  hvac_system: string;
  plumbing_system: string;
  electrical_system: string;
  environmental_harshness: string;
  soil_acidity: string;
  maintenance_frequency: string;
  material_quality: string;
}

const DEFAULT_FORM: FormState = {
  building_type: 'Residential',
  foundation_type: 'Raft',
  superstructure_type: 'Reinforced Concrete',
  roofing_material: 'Concrete Tile',
  exterior_finish: 'Painted Plaster',
  hvac_system: 'Central AC',
  plumbing_system: 'UPVC',
  electrical_system: 'Standard',
  environmental_harshness: '5',
  soil_acidity: '6.5',
  maintenance_frequency: '6',
  material_quality: '7',
};

// ── Helper: risk-level config ─────────────────────────────────────────────────

const RISK_CONFIG = {
  High: {
    label: 'High Risk',
    bg: 'bg-rose-50 border-rose-200',
    badge: 'bg-rose-100 text-rose-700 border border-rose-200',
    icon: ShieldAlert,
    iconClass: 'text-rose-500',
    bar: 'bg-rose-500',
    barWidth: 'w-1/4',
    textColor: 'text-rose-700',
  },
  Medium: {
    label: 'Medium Risk',
    bg: 'bg-amber-50 border-amber-200',
    badge: 'bg-amber-100 text-amber-700 border border-amber-200',
    icon: AlertTriangle,
    iconClass: 'text-amber-500',
    bar: 'bg-amber-400',
    barWidth: 'w-1/2',
    textColor: 'text-amber-700',
  },
  Low: {
    label: 'Low Risk',
    bg: 'bg-emerald-50 border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
    icon: CheckCircle2,
    iconClass: 'text-emerald-500',
    bar: 'bg-emerald-500',
    barWidth: 'w-3/4',
    textColor: 'text-emerald-700',
  },
};

// ── Slider input ──────────────────────────────────────────────────────────────

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
// ── Field options for dropdowns ──────────────────────────────────────────────

const FIELD_OPTIONS = {
  building_type: ['Residential', 'Commercial', 'Industrial', 'Institutional', 'Mixed-Use'],
  foundation_type: ['Strip', 'Pad', 'Raft', 'Pile', 'Caisson'],
  superstructure_type: ['Timber Frame', 'Masonry', 'Reinforced Concrete', 'Steel Frame', 'Composite'],
  roofing_material: ['Asphalt Shingle', 'Metal Sheet', 'Clay Tile', 'Concrete Tile', 'Membrane'],
  exterior_finish: ['Painted Plaster', 'EIFS', 'Exposed Brick', 'Stone Veneer', 'Cladding'],
  hvac_system: ['None', 'Natural Ventilation', 'Split AC', 'Central AC', 'VRF'],
  plumbing_system: ['Galvanized Steel', 'Cast Iron', 'UPVC', 'PEX', 'Copper'],
  electrical_system: ['Standard', 'Overhead', 'Underground', 'Solar-Integrated', 'None'],
};

// ── Select input ─────────────────────────────────────────────────────────────

interface SelectFieldProps {
  id: string;
  label: string;
  icon: React.ElementType;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}

function SelectField({ id, label, icon: Icon, value, options, onChange }: SelectFieldProps) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="flex items-center gap-1 text-[10px] font-semibold text-gray-600 uppercase tracking-wide"
      >
        <Icon className="h-3 w-3 text-orange-500 shrink-0" />
        <span className="truncate">{label}</span>
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-800
          focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent cursor-pointer"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}
// ── Main component ────────────────────────────────────────────────────────────

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
      building_type: form.building_type,
      foundation_type: form.foundation_type,
      superstructure_type: form.superstructure_type,
      roofing_material: form.roofing_material,
      exterior_finish: form.exterior_finish,
      hvac_system: form.hvac_system,
      plumbing_system: form.plumbing_system,
      electrical_system: form.electrical_system,
      environmental_harshness: parseFloat(form.environmental_harshness),
      soil_acidity: parseFloat(form.soil_acidity),
      maintenance_frequency: parseFloat(form.maintenance_frequency),
      material_quality: parseFloat(form.material_quality),
    };

    try {
      const response = await api.post<PredictionResponse>(
        '/v1/project/predict-lifecycle',
        payload,
      );
      setResult(response.data);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string }; status?: number } };
      if (axiosErr.response?.status === 503) {
        setError(
          'The ML model is not yet available on the server. ' +
            'Please ensure lifecycle_model.pkl is placed in backend/weights/ and the server is restarted.',
        );
      } else {
        const detail = axiosErr.response?.data?.detail;
        setError(
          typeof detail === 'string'
            ? detail
            : 'An unexpected error occurred. Please check the server and try again.',
        );
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
        {/* ── Left sidebar: input form ────────────────────────────────────── */}
        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden"
        >
          {/* Form header */}
          <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-50">
              <FlaskConical className="h-4 w-4 text-orange-500" />
            </span>
            <div>
              <p className="text-sm font-semibold text-gray-900">Input Parameters</p>
              <p className="text-[11px] text-gray-400">12 features — matches model training pipeline</p>
            </div>
          </div>

          {/* Fields */}
          <div className="overflow-y-auto max-h-[72vh] px-5 py-5 space-y-6">
            {/* ── Section: Structural System ────────────────────────────────── */}
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-orange-500 mb-3">
                Structural System
              </p>
              <div className="grid grid-cols-2 gap-3">
                <SelectField
                  id="building_type"
                  label="Building Type"
                  icon={Building2}
                  value={form.building_type}
                  options={FIELD_OPTIONS.building_type}
                  onChange={setField('building_type')}
                />
                <SelectField
                  id="foundation_type"
                  label="Foundation"
                  icon={Layers}
                  value={form.foundation_type}
                  options={FIELD_OPTIONS.foundation_type}
                  onChange={setField('foundation_type')}
                />
                <SelectField
                  id="superstructure_type"
                  label="Superstructure"
                  icon={HardHat}
                  value={form.superstructure_type}
                  options={FIELD_OPTIONS.superstructure_type}
                  onChange={setField('superstructure_type')}
                />
                <SelectField
                  id="roofing_material"
                  label="Roofing"
                  icon={Home}
                  value={form.roofing_material}
                  options={FIELD_OPTIONS.roofing_material}
                  onChange={setField('roofing_material')}
                />
                <SelectField
                  id="exterior_finish"
                  label="Exterior Finish"
                  icon={Paintbrush}
                  value={form.exterior_finish}
                  options={FIELD_OPTIONS.exterior_finish}
                  onChange={setField('exterior_finish')}
                />
                <SelectField
                  id="hvac_system"
                  label="HVAC"
                  icon={Wind}
                  value={form.hvac_system}
                  options={FIELD_OPTIONS.hvac_system}
                  onChange={setField('hvac_system')}
                />
                <SelectField
                  id="plumbing_system"
                  label="Plumbing"
                  icon={Droplets}
                  value={form.plumbing_system}
                  options={FIELD_OPTIONS.plumbing_system}
                  onChange={setField('plumbing_system')}
                />
                <SelectField
                  id="electrical_system"
                  label="Electrical"
                  icon={Zap}
                  value={form.electrical_system}
                  options={FIELD_OPTIONS.electrical_system}
                  onChange={setField('electrical_system')}
                />
              </div>
            </div>

            <div className="border-t border-gray-100" />

            {/* ── Section: Site & Condition Metrics ──────────────────────── */}
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-orange-500 mb-3">
                Site &amp; Condition Metrics
              </p>
              <div className="space-y-5">
                <SliderField
                  id="material_quality"
                  label="Material Quality"
                  description="Overall grade of the primary structural material. 1 = severely degraded, 10 = brand-new premium."
                  icon={HardHat}
                  value={form.material_quality}
                  min={1}
                  max={10}
                  step={1}
                  onChange={setField('material_quality')}
                />
                <SliderField
                  id="environmental_harshness"
                  label="Environmental Harshness"
                  description="Exposure severity. 1 = mild inland, 10 = extreme coastal / industrial / cyclone zone."
                  icon={Gauge}
                  value={form.environmental_harshness}
                  min={1}
                  max={10}
                  step={1}
                  onChange={setField('environmental_harshness')}
                />
                <SliderField
                  id="soil_acidity"
                  label="Soil Acidity (pH)"
                  description="Site soil pH. Values below 5.5 accelerate sub-structure corrosion. Neutral = 7.0."
                  icon={FlaskConical}
                  value={form.soil_acidity}
                  min={0}
                  max={14}
                  step={0.1}
                  onChange={setField('soil_acidity')}
                />
                <SliderField
                  id="maintenance_frequency"
                  label="Maintenance Interval"
                  description="Months between planned maintenance visits. 1 = monthly, 12 = annually."
                  icon={Wrench}
                  value={form.maintenance_frequency}
                  min={1}
                  max={12}
                  step={1}
                  unit=" mo"
                  onChange={setField('maintenance_frequency')}
                />
              </div>
            </div>
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
                  Analysing…
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

        {/* ── Right panel: results ────────────────────────────────────────── */}
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
                    <HardHat className="h-4 w-4 text-orange-500" />
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
                {/* Numeric metrics */}
                <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-gray-100 border-b border-gray-100">
                  {[
                    { label: 'Material Quality', value: result.input_echo.material_quality, unit: '/10' },
                    { label: 'Env. Harshness', value: result.input_echo.environmental_harshness, unit: '/10' },
                    { label: 'Soil Acidity', value: result.input_echo.soil_acidity, unit: ' pH' },
                    { label: 'Maint. Interval', value: result.input_echo.maintenance_frequency, unit: ' mo' },
                  ].map(({ label, value, unit }) => (
                    <div key={label} className="px-4 py-3 text-center">
                      <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide truncate">
                        {label}
                      </p>
                      <p className="mt-1 text-lg font-bold text-gray-800 tabular-nums">
                        {value}
                        <span className="text-xs font-normal text-gray-400">{unit}</span>
                      </p>
                    </div>
                  ))}
                </div>
                {/* Categorical features */}
                <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-y divide-gray-100">
                  {[
                    { label: 'Building', value: result.input_echo.building_type },
                    { label: 'Foundation', value: result.input_echo.foundation_type },
                    { label: 'Structure', value: result.input_echo.superstructure_type },
                    { label: 'Roofing', value: result.input_echo.roofing_material },
                    { label: 'Exterior', value: result.input_echo.exterior_finish },
                    { label: 'HVAC', value: result.input_echo.hvac_system },
                    { label: 'Plumbing', value: result.input_echo.plumbing_system },
                    { label: 'Electrical', value: result.input_echo.electrical_system },
                  ].map(({ label, value }) => (
                    <div key={label} className="px-4 py-2.5 text-center">
                      <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">
                        {label}
                      </p>
                      <p className="mt-0.5 text-xs font-semibold text-gray-700 leading-tight">
                        {value}
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
