// WI-4 (mockup 01 "Review upstream diff") — the upstream-merge review. Shows each field
// the upstream changed (ours vs theirs, + base & conflict for a 3-way), lets the user pick
// which upstream values to TAKE, then applies. "Keep all mine" re-pins without taking
// anything. Render-only; logic is in useMotifSync.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { useMotifSync } from '../hooks/useMotifSync';
import { isThreeWayField, type SyncDiff, type SyncField } from '../types';

function preview(v: unknown): string {
  const s = typeof v === 'string' ? v : JSON.stringify(v);
  return s.length > 90 ? `${s.slice(0, 90)}…` : s;
}
function upstreamChanged(f: SyncField): boolean {
  return isThreeWayField(f) ? f.theirs_changed : f.changed;
}

export function SyncDiffDrawer({ diff, sync, onClose }: {
  diff: SyncDiff;
  sync: ReturnType<typeof useMotifSync>;
  onClose: () => void;
}) {
  const { t } = useTranslation('composition');
  const [accept, setAccept] = useState<Set<string>>(new Set());
  const changed = Object.entries(diff.fields).filter(([, f]) => upstreamChanged(f));
  const toggle = (k: string) => setAccept((p) => {
    const n = new Set(p);
    if (n.has(k)) n.delete(k); else n.add(k);
    return n;
  });

  return (
    <div data-testid="sync-diff-drawer" className="flex flex-col gap-2 rounded border border-amber-300 bg-amber-50/60 p-2 text-[11px] dark:border-amber-800 dark:bg-amber-950/20">
      <div className="flex items-center justify-between">
        <span className="font-medium text-amber-800 dark:text-amber-200">
          {t('motif.sync.title', { defaultValue: 'Upstream update' })}
          <span className="ml-1 rounded bg-amber-200 px-1 text-[10px] text-amber-800 dark:bg-amber-900/60 dark:text-amber-200">
            {diff.diff_mode === 'three_way'
              ? t('motif.sync.threeWay', { defaultValue: '3-way' })
              : t('motif.sync.twoWay', { defaultValue: '2-way' })}
          </span>
        </span>
        <button type="button" data-testid="sync-diff-close" className="text-neutral-400 hover:text-neutral-600" onClick={onClose}>✕</button>
      </div>

      {changed.length === 0 ? (
        <p data-testid="sync-diff-nochange" className="text-neutral-500">
          {t('motif.sync.noChange', { defaultValue: 'The upstream advanced but no mergeable field changed.' })}
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {changed.map(([name, f]) => {
            const conflict = isThreeWayField(f) && f.conflict;
            return (
              <li key={name} data-testid={`sync-diff-field-${name}`} className="rounded border border-neutral-200 bg-white p-1.5 dark:border-neutral-700 dark:bg-neutral-900">
                <div className="mb-0.5 flex items-center justify-between">
                  <span className="font-medium text-neutral-700 dark:text-neutral-200">{name}</span>
                  {conflict && (
                    <span data-testid={`sync-diff-conflict-${name}`} className="rounded bg-rose-100 px-1 text-[10px] text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                      {t('motif.sync.conflict', { defaultValue: 'conflict — you both edited this' })}
                    </span>
                  )}
                </div>
                <div className="text-neutral-500"><span className="text-neutral-400">{t('motif.sync.mine', { defaultValue: 'mine' })}: </span>{preview(f.ours)}</div>
                <div className="text-emerald-700 dark:text-emerald-400"><span className="text-neutral-400">{t('motif.sync.theirs', { defaultValue: 'upstream' })}: </span>{preview(f.theirs)}</div>
                <label className="mt-1 flex items-center gap-1">
                  <input type="checkbox" data-testid={`sync-diff-accept-${name}`} checked={accept.has(name)} onChange={() => toggle(name)} />
                  <span>{t('motif.sync.take', { defaultValue: 'take upstream' })}</span>
                </label>
              </li>
            );
          })}
        </ul>
      )}

      {sync.apply.isError && (
        <p data-testid="sync-diff-error" className="text-rose-600 dark:text-rose-400">
          {(sync.apply.error as Error | null)?.message || t('motif.sync.error', { defaultValue: "Couldn't apply the merge." })}
        </p>
      )}

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          data-testid="sync-diff-keep-mine"
          disabled={sync.apply.isPending}
          className="rounded border border-neutral-300 px-2 py-0.5 disabled:opacity-50 dark:border-neutral-600"
          onClick={() => sync.apply.mutate([])}
        >
          {t('motif.sync.keepMine', { defaultValue: 'Keep all mine' })}
        </button>
        <button
          type="button"
          data-testid="sync-diff-apply"
          disabled={sync.apply.isPending || accept.size === 0}
          className="rounded bg-amber-600 px-2 py-0.5 font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          onClick={() => sync.apply.mutate([...accept])}
        >
          {sync.apply.isPending
            ? t('motif.sync.applying', { defaultValue: 'Applying…' })
            : t('motif.sync.apply', { n: accept.size, defaultValue: 'Take {{n}} from upstream' })}
        </button>
      </div>
    </div>
  );
}
