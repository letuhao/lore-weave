import { useTranslation } from 'react-i18next';
import { Plus, X } from 'lucide-react';
import { PROFILE_KINDS, type DimensionAdd, type DimensionOverrides } from '../types';

/** Edits the per-kind `add` dimensions (the genre-dimension layer AI-suggest fills).
 *  `remove`/`relabel`/`reweight` ops are preserved untouched (round-trip safe) — the
 *  v1 UI only edits `add`. Controlled: emits the full overrides map on every change. */
export function DimensionOverrideEditor({
  value,
  onChange,
}: {
  value: DimensionOverrides;
  onChange: (next: DimensionOverrides) => void;
}) {
  const { t } = useTranslation('enrichment');

  const setKindAdd = (kind: string, adds: DimensionAdd[]) => {
    const ops = { ...(value[kind] ?? {}) };
    if (adds.length) ops.add = adds;
    else delete ops.add;
    const next = { ...value };
    if (Object.keys(ops).length) next[kind] = ops;
    else delete next[kind];
    onChange(next);
  };

  const updateRow = (kind: string, i: number, patch: Partial<DimensionAdd>) => {
    const adds = [...(value[kind]?.add ?? [])];
    adds[i] = { ...adds[i], ...patch };
    setKindAdd(kind, adds);
  };

  return (
    <div className="space-y-3" data-testid="dimension-override-editor">
      {PROFILE_KINDS.map((kind) => {
        const adds = value[kind]?.add ?? [];
        return (
          <div key={kind} className="rounded border bg-card p-2" data-testid={`override-kind-${kind}`}>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-xs font-medium">{t(`settings.kind.${kind}`)}</span>
              <button
                type="button"
                data-testid={`override-add-${kind}`}
                onClick={() => setKindAdd(kind, [...adds, { id: '', label: '', weight: 2, required: false }])}
                className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
              >
                <Plus className="h-3 w-3" /> {t('settings.add_dimension')}
              </button>
            </div>
            {adds.length === 0 ? (
              <p className="text-[11px] text-muted-foreground">{t('settings.no_extra_dims')}</p>
            ) : (
              <div className="space-y-1.5">
                {adds.map((d, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-1.5 text-[11px]">
                    <input
                      aria-label={t('settings.dim_id')}
                      placeholder={t('settings.dim_id')}
                      value={d.id}
                      onChange={(e) => updateRow(kind, i, { id: e.target.value })}
                      className="w-28 rounded border bg-background px-1.5 py-0.5"
                    />
                    <input
                      aria-label={t('settings.dim_label')}
                      placeholder={t('settings.dim_label')}
                      value={d.label ?? ''}
                      onChange={(e) => updateRow(kind, i, { label: e.target.value })}
                      className="w-32 rounded border bg-background px-1.5 py-0.5"
                    />
                    <input
                      aria-label={t('settings.dim_weight')}
                      type="number"
                      min={0}
                      step={0.5}
                      value={d.weight ?? 2}
                      onChange={(e) => updateRow(kind, i, { weight: Number(e.target.value) })}
                      className="w-16 rounded border bg-background px-1.5 py-0.5"
                    />
                    <label className="inline-flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={!!d.required}
                        onChange={(e) => updateRow(kind, i, { required: e.target.checked })}
                      />
                      {t('settings.dim_required')}
                    </label>
                    <button
                      type="button"
                      aria-label={t('settings.remove_dimension')}
                      data-testid={`override-remove-${kind}-${i}`}
                      onClick={() => setKindAdd(kind, adds.filter((_, j) => j !== i))}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
