import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import type { EntityKind, UnknownEntity } from '../types';

export type ResolveResult =
  | { strategy: 'existing'; kindId: string }
  | { strategy: 'new'; code: string; name: string };

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
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const code = entity.source_kind_code;
  // How many other parked entities arrived under the same source code. Shown as CONTEXT only.
  // It used to gate an "apply to all" checkbox, pre-checked, that routed through
  // `POST /kind-aliases` — removed in SS-4, live-probed at 405. So the default action of this
  // modal could only fail. The count is still worth telling the author (it says how much work is
  // left), but the bulk promise it carried — "future extractions with this code resolve
  // automatically" — belongs to the alias row, and that returns in SS-7.
  const othersWithSameCode = code ? Math.max(sameCodeCount - 1, 0) : 0;

  // Radix Dialog.Root (inside FormDialog) handles Escape/outside-click → onOpenChange(false);
  // the `!saving` guard (block dismissal mid-submit) moves into that callback below.

  const handleSubmit = async () => {
    setError('');
    let payload: ResolveResult;
    if (strategy === 'existing') {
      if (!kindId) { setError(t('unknown.err_pick_kind')); return; }
      payload = { strategy: 'existing', kindId };
    } else {
      const c = newCode.trim().toLowerCase();
      const n = newName.trim();
      if (!c || !n) { setError(t('unknown.err_new_kind')); return; }
      if (!/^[a-z0-9_]+$/.test(c)) { setError(t('unknown.err_code_format')); return; }
      payload = { strategy: 'new', code: c, name: n };
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
    <FormDialog
      open
      onOpenChange={(nextOpen) => { if (!nextOpen && !saving) onClose(); }}
      title={t('unknown.resolve_title')}
      description={entity.name || t('unknown.unnamed')}
      size="md"
      footer={
        <>
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
        </>
      }
    >
      <div className="flex flex-col gap-4">
            {/* Visual echo of the source kind code (FormDialog's `description` above stays plain
                text for a11y — this keeps the monospace badge FormDialog's template can't hold). */}
            {code && (
              <span className="-mt-2 inline-block w-fit rounded bg-secondary px-1.5 py-px font-mono text-[10px] text-muted-foreground">{code}</span>
            )}
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

            {/* Context, not an action: how many others are still parked under this code. */}
            {othersWithSameCode > 0 && (
              <p data-testid="resolve-same-code-count" className="rounded-md border bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">
                {t('unknown.same_code_note', {
                  count: othersWithSameCode,
                  code,
                  defaultValue: '{{count}} more entities arrived as "{{code}}" — resolve each one here.',
                })}
              </p>
            )}

            {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </FormDialog>
  );
}
