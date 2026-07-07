import { cn } from '@/lib/utils';
import type { ContextTraceFrame } from '../types';
import { gaugeState, kfmt, statusMeta, turnReductionPct } from './inspectorMath';

// The Inspector hero — a semicircle context-pressure gauge (compiled fill, target
// tick, color state) + the raw / compiled / reduction numbers + the full status
// chip list. Pure render; all math is in inspectorMath. verify-by-effect: the
// gauge stroke color reflects gaugeState (data-gauge-state), the tick sits at the
// target, and over-target/over-ceiling turns render the warning/destructive hue.

const STATE_STROKE: Record<string, string> = {
  under: 'stroke-emerald-400',
  'over-target': 'stroke-yellow-400',
  'over-ceiling': 'stroke-red-400',
};
const STATE_TEXT: Record<string, string> = {
  under: 'text-emerald-400',
  'over-target': 'text-yellow-400',
  'over-ceiling': 'text-red-400',
};

export function PressureGauge({ frame }: { frame: ContextTraceFrame }) {
  const compiled = frame.used_tokens;
  const target = frame.target ?? null;
  const ceiling = frame.context_length ?? null;
  const raw = frame.raw_tokens ?? null;
  const reduction = turnReductionPct(frame);
  const state = gaugeState(compiled, target, ceiling);
  const caching = frame.caching;
  // Only worth a row when the provider actually declares a caching capability —
  // a "stateless" strategy has no cache split to show (always 0% hit, every turn).
  const showCaching = !!caching && caching.strategy !== 'stateless';

  // Gauge geometry: a semicircle scaled to 2×target for readability (so a healthy
  // compiled≈target lands mid-arc). Falls back to the ceiling, else the compiled
  // value, when target is unknown.
  const scale = (target ?? ceiling ?? (compiled || 1)) * 2;
  const pct = Math.min(1, compiled / scale);
  const tPct = target != null ? Math.min(1, target / scale) : null;
  const R = 90;
  const C = Math.PI * R;

  return (
    <div className="rounded-xl border border-border bg-card p-5" data-testid="inspector-gauge">
      <div className="flex flex-wrap items-center gap-7">
        <div className="relative shrink-0" style={{ width: 200, height: 120 }}>
          <svg width="200" height="120" viewBox="0 0 200 120" data-gauge-state={state}>
            <path
              d="M10 110 A90 90 0 0 1 190 110"
              fill="none"
              className="stroke-secondary"
              strokeWidth="14"
              strokeLinecap="round"
            />
            <path
              d="M10 110 A90 90 0 0 1 190 110"
              fill="none"
              className={cn(STATE_STROKE[state], 'transition-[stroke-dashoffset] duration-500')}
              strokeWidth="14"
              strokeLinecap="round"
              strokeDasharray={C}
              strokeDashoffset={C * (1 - pct)}
            />
            {tPct != null && (
              <line
                x1={100 - Math.cos(Math.PI * tPct) * 90}
                y1={110 - Math.sin(Math.PI * tPct) * 90}
                x2={100 - Math.cos(Math.PI * tPct) * 72}
                y2={110 - Math.sin(Math.PI * tPct) * 72}
                className="stroke-yellow-400"
                strokeWidth="2.5"
                data-testid="gauge-target-tick"
              />
            )}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
            <div className={cn('font-mono text-2xl font-bold', STATE_TEXT[state])}>
              {kfmt(compiled)}
            </div>
            <div className="font-mono text-[10px] text-muted-foreground">
              / {target != null ? kfmt(target) : '—'} target
            </div>
          </div>
        </div>

        <div className="grid flex-1 grid-cols-3 gap-4">
          <Num label="raw (naive)" value={raw != null ? raw.toLocaleString() : '—'} className="text-red-400" />
          <Num label="compiled sent" value={compiled.toLocaleString()} className="text-emerald-400" />
          <Num
            label="reduction"
            value={reduction != null ? `−${Math.round(reduction)}%` : '—'}
            className="text-green-400"
          />
          <div className="col-span-3 mt-1 flex flex-wrap gap-1.5">
            {(frame.status_flags ?? []).map((f) => {
              const m = statusMeta(f);
              return (
                <span
                  key={f}
                  className={cn(
                    'inline-flex items-center rounded-full border border-border bg-secondary px-2 py-0.5 text-[11px] font-semibold',
                    m.className,
                  )}
                  data-status-chip={f}
                >
                  {m.label}
                </span>
              );
            })}
          </div>
          {showCaching && caching && <CachingRow caching={caching} />}
        </div>
      </div>
    </div>
  );
}

function CachingRow({ caching }: { caching: NonNullable<ContextTraceFrame['caching']> }) {
  const hitPct = Math.round(caching.hit_rate * 100);
  const savingPct = Math.round(caching.cost_delta_ratio * 100);
  const savingLabel = savingPct >= 0 ? `saving ${savingPct}%` : `costing ${Math.abs(savingPct)}% more`;
  return (
    <div
      className="col-span-3 flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-muted-foreground"
      data-testid="inspector-caching-row"
    >
      <span
        className={cn(
          'inline-flex items-center rounded-full border border-border bg-secondary px-2 py-0.5 font-semibold',
          caching.thrashing ? 'text-red-400' : savingPct >= 0 ? 'text-emerald-400' : 'text-yellow-400',
        )}
      >
        cache: {hitPct}% hit · {savingLabel}
      </span>
      {caching.thrashing && (
        <span
          className="inline-flex items-center rounded-full border border-border bg-secondary px-2 py-0.5 font-semibold text-red-400"
          data-status-chip="cache-thrashing"
        >
          thrashing
        </span>
      )}
    </div>
  );
}

function Num({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn('font-mono text-xl font-bold', className)}>{value}</div>
    </div>
  );
}
