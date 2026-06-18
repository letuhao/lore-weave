// LOOM Composition (T0.1) — plot-thread / promise-debt panel (view).
//
// Surfaces the open-promise debt ledger (FD-1 S4a) so the author sees the unpaid
// promises (priority-ordered) + an open-count badge. ADVISORY (D4) — read-only,
// never gates generation/commit. Gated by the host on
// work.settings.narrative_thread_enabled; the `enabled` guard keeps the panel
// self-contained (and unit-testable). P0 meta = kind + status + summary
// (chapter# / due-soon deferred per the spec Decisions). Error is inline (read
// query — a render-time toast would re-fire), matching GroundingPanel.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNarrativeThreads } from '../hooks/useNarrativeThreads';
import type { ThreadStatus } from '../types';

// status → row token (icon + class). open/progressing = unpaid (warn); paid =
// locked (success); dropped = muted/struck.
const TOKEN: Record<ThreadStatus, { icon: string; cls: string }> = {
  open: { icon: '🔓', cls: 'text-amber-600' },
  progressing: { icon: '🔓', cls: 'text-amber-600' },
  paid: { icon: '🔒', cls: 'text-emerald-600' },
  dropped: { icon: '⊘', cls: 'text-neutral-400 line-through' },
};

export function ThreadsPanel(
  { projectId, token, enabled }: { projectId: string; token: string | null; enabled: boolean },
) {
  const { t } = useTranslation('composition');
  const [status, setStatus] = useState<'open' | 'all'>('open');
  // Disabled → no query (undefined projectId) + null render below.
  const q = useNarrativeThreads(enabled ? projectId : undefined, token, status);

  if (!enabled) return null;

  const threads = q.data?.threads ?? [];
  const openCount = q.data?.open_count ?? 0;

  return (
    <div className="flex flex-col gap-2 p-3 text-sm" data-testid="composition-threads">
      <div className="flex items-center justify-between">
        <span className="font-medium">{t('threadsTitle', { defaultValue: 'Plot threads' })}</span>
        <span
          data-testid="composition-threads-open-count"
          data-count={openCount}
          className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-700 dark:bg-amber-950 dark:text-amber-300"
        >
          {t('threadOpenCount', { count: openCount, defaultValue: '{{count}} open' })}
        </span>
      </div>

      {/* open ⇄ all filter */}
      <div className="flex gap-1 text-xs" role="tablist" aria-label={t('threadsTitle', { defaultValue: 'Plot threads' })}>
        {(['open', 'all'] as const).map((s) => (
          <button
            key={s}
            type="button"
            data-testid={`composition-threads-filter-${s}`}
            role="tab"
            aria-selected={status === s}
            className={`rounded px-2 py-0.5 ${status === s ? 'bg-neutral-200 font-medium dark:bg-neutral-700' : 'text-neutral-500'}`}
            onClick={() => setStatus(s)}
          >
            {s === 'open'
              ? t('threadFilterOpen', { defaultValue: 'Open' })
              : t('threadFilterAll', { defaultValue: 'All' })}
          </button>
        ))}
      </div>

      {q.isLoading && <div className="text-neutral-500">{t('loading', { defaultValue: 'Loading…' })}</div>}
      {q.isError && (
        <div
          data-testid="composition-threads-error"
          className="rounded bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950 dark:text-red-300"
        >
          {t('threadsError', { defaultValue: 'Could not load plot threads.' })}
        </div>
      )}

      <ul className="flex flex-col gap-1">
        {threads.map((th) => {
          const tok = TOKEN[th.status];
          const kind = t(`threadKind_${th.kind}`, { defaultValue: th.kind });
          return (
            <li
              key={th.id}
              data-testid="composition-thread"
              data-status={th.status}
              className="flex items-start justify-between gap-2 rounded border border-neutral-200 p-2 dark:border-neutral-700"
            >
              <span className={tok.cls}>
                <span className="mr-1" aria-hidden>{tok.icon}</span>
                {th.summary || kind}
              </span>
              <span className="shrink-0 text-[11px] text-neutral-400">
                {th.status === 'paid' && <span className="mr-1 text-emerald-600">{t('threadPaid', { defaultValue: 'paid' })}</span>}
                {th.status === 'dropped' && <span className="mr-1">{t('threadDropped', { defaultValue: 'dropped' })}</span>}
                {kind}
              </span>
            </li>
          );
        })}
        {!q.isLoading && !q.isError && threads.length === 0 && (
          <li data-testid="composition-threads-empty" className="text-xs text-neutral-500">
            {status === 'open'
              ? t('noOpenThreads', { defaultValue: 'No open promises — all paid.' })
              : t('noThreads', { defaultValue: 'No threads yet.' })}
          </li>
        )}
      </ul>
    </div>
  );
}
