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
  { projectId, token, enabled, focusThreadId }: {
    projectId: string;
    token: string | null;
    enabled: boolean;
    /** 24 PH18 — the Plan Hub's thread badge deep-links here. `narrative_thread.id` IS what this
     *  panel lists, so unlike the canon lens it can focus the exact row. Highlighted + hoisted, not
     *  filtered: the panel is still the whole promise ledger. */
    focusThreadId?: string | null;
  },
) {
  const { t } = useTranslation('composition');
  const [status, setStatus] = useState<'open' | 'all'>('open');
  // Disabled → no query (undefined projectId) + null render below.
  const q = useNarrativeThreads(enabled ? projectId : undefined, token, status);

  if (!enabled) return null;

  const raw = q.data?.threads ?? [];
  // Hoist the focused thread to the top so a deep-link lands on something visible, without hiding
  // the rest. A link that opens a long list and highlights nothing on screen is the same silent
  // no-op as a link that filters to nothing.
  const threads = focusThreadId
    ? [...raw].sort((a, b) => Number(b.id === focusThreadId) - Number(a.id === focusThreadId))
    : raw;
  const openCount = q.data?.open_count ?? 0;
  // The thread may not be in the CURRENT filter (it could be paid/archived while the filter is
  // "open"). Say so rather than leaving the user hunting a highlight that isn't there.
  const focusMissing = !!focusThreadId && !raw.some((th) => th.id === focusThreadId);

  return (
    <div className="flex flex-col gap-2 p-3 text-sm" data-testid="composition-threads">
      {focusMissing && (
        <div
          data-testid="composition-threads-focus-missing"
          className="rounded bg-sky-50 p-2 text-[11px] text-sky-800 dark:bg-sky-950 dark:text-sky-300"
        >
          {t('threadFocusMissing', {
            defaultValue:
              'The promise you came from is not in this view — it may already be paid. Switch the filter to “all”.',
          })}
        </div>
      )}
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
              data-focused={th.id === focusThreadId ? 'true' : undefined}
              className={`flex items-start justify-between gap-2 rounded border p-2 ${
                th.id === focusThreadId
                  ? 'border-sky-400 ring-2 ring-sky-400 dark:border-sky-700'
                  : 'border-neutral-200 dark:border-neutral-700'
              }`}
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
