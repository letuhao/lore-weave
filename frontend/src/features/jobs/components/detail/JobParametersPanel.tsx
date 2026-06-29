import { useTranslation } from 'react-i18next';

import type { JobParams } from '../../types';

/** Render one param value: scalars as-is, arrays joined, objects as compact JSON,
 *  null/undefined as an em-dash. Keeps the panel schema-free — whatever the
 *  producer put in `params` shows up (model now, effort later, no FE change). */
function renderValue(v: unknown): string {
  if (v == null) return '—';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') return v.toLocaleString();
  if (typeof v === 'string') return v || '—';
  if (Array.isArray(v)) return v.length ? v.map((x) => String(x)).join(' · ') : '—';
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

// bug #37 — these call-count keys are rendered specially in the Progress panel
// ("LLM calls: done / total"), so keep them out of the raw key/value grid here.
const _PROGRESS_KEYS = new Set(['estimated_llm_calls', 'llm_calls_done']);

/** Dynamic parameters panel — a key/value grid built from the job's `params` JSONB.
 *  Renders nothing when there are no params (avoids an empty card). */
export function JobParametersPanel({ params }: { params: JobParams | null }) {
  const { t } = useTranslation('jobs');
  const entries = params
    ? Object.entries(params).filter(([k]) => !_PROGRESS_KEYS.has(k))
    : [];
  if (entries.length === 0) return null;

  return (
    <div className="rounded-xl border bg-card">
      <div className="border-b px-4 py-3 text-sm font-semibold">
        {t('detail.parameters', { defaultValue: 'Parameters' })}{' '}
        <span className="text-[11px] font-normal text-muted-foreground">
          · {t('detail.parametersHint', { defaultValue: "dynamic, from the job's params object" })}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-x-8 gap-y-1 p-4 text-sm sm:grid-cols-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b py-1">
            <span className="text-muted-foreground">{k}</span>
            <span className="truncate text-right font-mono text-xs">{renderValue(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
