import { useTranslation } from 'react-i18next';
import { Plus, X } from 'lucide-react';
import {
  PROFILE_KINDS,
  type DimensionAdd,
  type DimensionOverrideOps,
  type DimensionOverrides,
} from '../types';
import { useComposeDimensions } from '../hooks/useComposeDimensions';

/** Per-kind dimension overrides (#3): the author can ADD custom dimensions AND
 *  relabel / reweight / remove (hide) the kind's BUILT-IN dimensions. The base set is
 *  fetched per kind (`base=true`, profile-localized) so the controls are non-blind;
 *  only DELTAS are stored (a relabel/reweight that equals the base is not persisted).
 *  Controlled — emits the full overrides map on every change. */
export function DimensionOverrideEditor({
  bookId,
  value,
  onChange,
}: {
  bookId: string;
  value: DimensionOverrides;
  onChange: (next: DimensionOverrides) => void;
}) {
  const setKind = (kind: string, ops: DimensionOverrideOps) => {
    const next = { ...value };
    if (Object.keys(ops).length) next[kind] = ops;
    else delete next[kind];
    onChange(next);
  };

  return (
    <div className="space-y-3" data-testid="dimension-override-editor">
      {PROFILE_KINDS.map((kind) => (
        <KindOverrides
          key={kind}
          bookId={bookId}
          kind={kind}
          ops={value[kind] ?? {}}
          onChange={(ops) => setKind(kind, ops)}
        />
      ))}
    </div>
  );
}

/** Drop empty sub-ops so the stored override dict stays minimal (and a kind with no
 *  ops is dropped by the parent). */
function prune(ops: DimensionOverrideOps): DimensionOverrideOps {
  const next: DimensionOverrideOps = { ...ops };
  if (!next.add?.length) delete next.add;
  if (!next.remove?.length) delete next.remove;
  if (next.relabel && Object.keys(next.relabel).length === 0) delete next.relabel;
  if (next.reweight && Object.keys(next.reweight).length === 0) delete next.reweight;
  return next;
}

function KindOverrides({
  bookId,
  kind,
  ops,
  onChange,
}: {
  bookId: string;
  kind: string;
  ops: DimensionOverrideOps;
  onChange: (ops: DimensionOverrideOps) => void;
}) {
  const { t } = useTranslation('enrichment');
  const baseDims = useComposeDimensions(bookId, kind, { base: true });
  const adds = ops.add ?? [];
  const removed = new Set(ops.remove ?? []);

  const emit = (patch: Partial<DimensionOverrideOps>) => onChange(prune({ ...ops, ...patch }));

  // ── built-in dims: relabel / reweight / remove (store deltas vs the base) ──
  const setRelabel = (id: string, label: string, base: string) => {
    const rel = { ...(ops.relabel ?? {}) };
    if (label.trim() && label.trim() !== base) rel[id] = label.trim();
    else delete rel[id];
    emit({ relabel: rel });
  };
  const setReweight = (id: string, w: number, base: number) => {
    const rw = { ...(ops.reweight ?? {}) };
    // weight must be > 0 (BE rejects <=0; to disable a dim the author HIDES it).
    // A cleared input (NaN) or a 0 → drop the delta → revert to the base weight.
    if (Number.isFinite(w) && w > 0 && w !== base) rw[id] = w;
    else delete rw[id];
    emit({ reweight: rw });
  };
  const toggleRemove = (id: string, on: boolean) => {
    const rm = new Set(ops.remove ?? []);
    if (on) rm.add(id);
    else rm.delete(id);
    emit({ remove: [...rm] });
  };

  // ── custom add rows (unchanged behavior) ──
  const setAdds = (a: DimensionAdd[]) => emit({ add: a });
  const updateAdd = (i: number, patch: Partial<DimensionAdd>) => {
    const a = [...adds];
    a[i] = { ...a[i], ...patch };
    setAdds(a);
  };

  return (
    <div className="rounded border bg-card p-2" data-testid={`override-kind-${kind}`}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-medium">{t(`settings.kind.${kind}`)}</span>
        <button
          type="button"
          data-testid={`override-add-${kind}`}
          onClick={() => setAdds([...adds, { id: '', label: '', weight: 2, required: false }])}
          className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
        >
          <Plus className="h-3 w-3" /> {t('settings.add_dimension')}
        </button>
      </div>

      {/* built-in dimensions — relabel / reweight / hide */}
      {baseDims.length > 0 && (
        <div className="mb-2 space-y-1" data-testid={`override-base-${kind}`}>
          {baseDims.map((d) => {
            const isRemoved = removed.has(d.id);
            const baseWeight = d.weight ?? 2;
            return (
              <div
                key={d.id}
                className={`flex flex-wrap items-center gap-1.5 text-[11px] ${isRemoved ? 'opacity-50' : ''}`}
              >
                {d.required && (
                  <span
                    title={t('settings.dim_required')}
                    data-testid={`override-required-${kind}-${d.id}`}
                    className="text-amber-600"
                  >
                    ★
                  </span>
                )}
                <input
                  aria-label={`${t('settings.dim_label')} ${d.id}`}
                  value={ops.relabel?.[d.id] ?? d.label}
                  disabled={isRemoved}
                  onChange={(e) => setRelabel(d.id, e.target.value, d.label)}
                  className="w-32 rounded border bg-background px-1.5 py-0.5 disabled:opacity-60"
                />
                <input
                  aria-label={`${t('settings.dim_weight')} ${d.id}`}
                  type="number"
                  min={0.5}
                  step={0.5}
                  value={ops.reweight?.[d.id] ?? baseWeight}
                  disabled={isRemoved}
                  onChange={(e) => setReweight(d.id, Number(e.target.value), baseWeight)}
                  className="w-16 rounded border bg-background px-1.5 py-0.5 disabled:opacity-60"
                />
                <label className="inline-flex items-center gap-1">
                  <input
                    type="checkbox"
                    data-testid={`override-hide-${kind}-${d.id}`}
                    checked={isRemoved}
                    onChange={(e) => toggleRemove(d.id, e.target.checked)}
                  />
                  {t('settings.hide')}
                </label>
              </div>
            );
          })}
        </div>
      )}

      {/* custom (author/AI-added) dimensions */}
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
                onChange={(e) => updateAdd(i, { id: e.target.value })}
                className="w-28 rounded border bg-background px-1.5 py-0.5"
              />
              <input
                aria-label={t('settings.dim_label')}
                placeholder={t('settings.dim_label')}
                value={d.label ?? ''}
                onChange={(e) => updateAdd(i, { label: e.target.value })}
                className="w-32 rounded border bg-background px-1.5 py-0.5"
              />
              <input
                aria-label={t('settings.dim_weight')}
                type="number"
                min={0.5}
                step={0.5}
                value={d.weight ?? 2}
                onChange={(e) => updateAdd(i, { weight: Number(e.target.value) })}
                className="w-16 rounded border bg-background px-1.5 py-0.5"
              />
              <label className="inline-flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={!!d.required}
                  onChange={(e) => updateAdd(i, { required: e.target.checked })}
                />
                {t('settings.dim_required')}
              </label>
              <button
                type="button"
                aria-label={t('settings.remove_dimension')}
                data-testid={`override-remove-${kind}-${i}`}
                onClick={() => setAdds(adds.filter((_, j) => j !== i))}
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
}
