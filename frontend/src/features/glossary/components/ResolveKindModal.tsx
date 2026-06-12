import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import type { EntityKind, UnknownEntity } from '../types';

export type ResolveResult =
  | { strategy: 'existing'; kindId: string; applyAll: boolean }
  | { strategy: 'new'; code: string; name: string; applyAll: boolean };

type Props = {
  entity: UnknownEntity;
  /** Reassign targets — real kinds only (no hidden, no 'unknown'). */
  kinds: EntityKind[];
  /** How many unknown entities share entity.source_kind_code (drives "merge all"). */
  sameCodeCount: number;
  onResolve: (r: ResolveResult) => Promise<void>;
  onClose: () => void;
};

export function ResolveKindModal({ entity, kinds, sameCodeCount, onResolve, onClose }: Props) {
  const { t } = useTranslation('glossaryEditor');
  const [strategy, setStrategy] = useState<'existing' | 'new'>('existing');
  const [kindId, setKindId] = useState(kinds[0]?.kind_id ?? '');
  const [newCode, setNewCode] = useState('');
  const [newName, setNewName] = useState('');
  const [applyAll, setApplyAll] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const code = entity.source_kind_code;
  const canMergeAll = !!code && sameCodeCount > 1;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !saving) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, saving]);

  const handleSubmit = async () => {
    setError('');
    const merge = canMergeAll && applyAll;
    let payload: ResolveResult;
    if (strategy === 'existing') {
      if (!kindId) { setError(t('unknown.err_pick_kind')); return; }
      payload = { strategy: 'existing', kindId, applyAll: merge };
    } else {
      const c = newCode.trim().toLowerCase();
      const n = newName.trim();
      if (!c || !n) { setError(t('unknown.err_new_kind')); return; }
      if (!/^[a-z0-9_]+$/.test(c)) { setError(t('unknown.err_code_format')); return; }
      payload = { strategy: 'new', code: c, name: n, applyAll: merge };
    }
    setSaving(true);
    try {
      await onResolve(payload);
    } catch (e) {
      setError((e as Error).message || t('unknown.err_save'));
      setSaving(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-xl border bg-background shadow-2xl" onClick={(e) => e.stopPropagation()}>
          {/* Header */}
          <div className="flex items-center justify-between border-b bg-card px-5 py-4">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{t('unknown.resolve_title')}</div>
              <div className="truncate text-[11px] text-muted-foreground">
                {entity.name || t('unknown.unnamed')}
                {code && <span className="ml-1.5 rounded bg-secondary px-1.5 py-px font-mono text-[10px]">{code}</span>}
              </div>
            </div>
            <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Body */}
          <div className="flex flex-col gap-4 p-5">
            {/* Strategy toggle */}
            <div className="flex gap-1.5">
              {(['existing', 'new'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setStrategy(s)}
                  data-testid={`resolve-strategy-${s}`}
                  className={
                    'flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ' +
                    (strategy === s ? 'border-primary/40 bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-secondary')
                  }
                >
                  {t(`unknown.strategy_${s}`)}
                </button>
              ))}
            </div>

            {strategy === 'existing' ? (
              <div>
                <label className="mb-1.5 block text-xs font-medium">{t('unknown.target_kind')}</label>
                <select
                  value={kindId}
                  onChange={(e) => setKindId(e.target.value)}
                  data-testid="resolve-kind-select"
                  className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                >
                  {kinds.map((k) => (
                    <option key={k.kind_id} value={k.kind_id}>{k.icon} {k.name}</option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <div>
                  <label className="mb-1.5 block text-xs font-medium">{t('unknown.new_kind_name')} <span className="text-destructive">*</span></label>
                  <input
                    autoFocus
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    data-testid="resolve-new-name"
                    placeholder={t('unknown.new_kind_name_ph')}
                    className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium">{t('unknown.new_kind_code')} <span className="text-destructive">*</span></label>
                  <input
                    value={newCode}
                    onChange={(e) => setNewCode(e.target.value)}
                    data-testid="resolve-new-code"
                    placeholder={code ?? t('unknown.new_kind_code_ph')}
                    className="w-full rounded-md border bg-background px-3 py-1.5 font-mono text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
                  />
                  <p className="mt-1 text-[10px] text-muted-foreground">{t('unknown.new_kind_code_hint')}</p>
                </div>
              </div>
            )}

            {/* Merge-all scope */}
            {canMergeAll && (
              <label className="flex items-start gap-2 rounded-md border bg-secondary/30 px-3 py-2 text-xs">
                <input type="checkbox" checked={applyAll} onChange={(e) => setApplyAll(e.target.checked)} data-testid="resolve-merge-all" className="mt-0.5" />
                <span>
                  {t('unknown.merge_all', { count: sameCodeCount, code })}
                  <span className="mt-0.5 block text-[10px] text-muted-foreground">{t('unknown.merge_all_hint')}</span>
                </span>
              </label>
            )}

            {error && <p className="text-xs text-destructive">{error}</p>}

            {/* Footer */}
            <div className="flex justify-end gap-2 border-t pt-4">
              <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary transition-colors">
                {t('unknown.cancel')}
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={saving}
                data-testid="resolve-apply"
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {saving ? t('unknown.saving') : t('unknown.apply')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
