// 22-C2 — the `scene-browser` dock panel: a book-wide table that renders the UNION of the
// book-service scene index and the composition spec (spec 22 §GUI). It reads book-service, not
// outline_node, so an imported book's scenes show even before any composition Work exists (the
// empty-rail bug, fixed at the root). Provenance is colour-ticked: teal = identity (book-service),
// amber = intent (composition). Logic lives in useSceneBrowser; this file only renders.
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { AlertTriangle, FileWarning, Search, Trash2 } from 'lucide-react';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import type { OutlineNode } from '@/features/composition/types';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { useSceneBrowser } from './useSceneBrowser';
import { useConformanceStatus } from './useConformanceStatus';
import { useSceneBulk, type BulkResult } from './useSceneBulk';
import type { SceneUnionRow } from './sceneUnion';

const STATUS_LABEL: Record<string, string> = {
  empty: 'Empty', outline: 'Outline', drafting: 'Drafting', done: 'Done',
};
const BULK_STATUSES: OutlineNode['status'][] = ['empty', 'outline', 'drafting', 'done'];

// 22-C2b — the bulk-action bar (module-level so it never remounts on a parent re-render). Shown
// only when >=1 spec-backed row is selected; applies a status to all, trashes all, and reports the
// honest partial-failure count from the last run.
function BulkBar({ count, busy, onStatus, onWords, onTrash, onClear, t }: {
  count: number; busy: boolean;
  onStatus: (s: OutlineNode['status']) => void; onWords: (n: number) => void; onTrash: () => void; onClear: () => void;
  t: (k: string, o?: Record<string, unknown>) => string;
}) {
  const commitWords = (e: React.FocusEvent<HTMLInputElement> | React.KeyboardEvent<HTMLInputElement>) => {
    const el = e.currentTarget;
    // Round BEFORE the >0 guard, else 0<n<0.5 rounds to 0 and (now that the BE persists target_words)
    // would zero every selected scene (review). A blank/non-positive/NaN value is ignored.
    const n = Math.round(Number(el.value));
    if (el.value.trim() !== '' && Number.isFinite(n) && n > 0) { onWords(n); el.value = ''; }
  };
  return (
    <div data-testid="scene-browser-bulkbar" className="flex flex-wrap items-center gap-2 border-b bg-primary/5 px-3 py-1.5 text-xs">
      <span data-testid="scene-browser-bulk-count" className="font-medium">
        {t('panels.scene-browser.bulk.count', { defaultValue: '{{n}} selected', n: count })}
      </span>
      <select
        data-testid="scene-browser-bulk-status" value="" disabled={busy}
        onChange={(e) => { if (e.target.value) onStatus(e.target.value as OutlineNode['status']); e.currentTarget.value = ''; }}
        aria-label={t('panels.scene-browser.bulk.setStatus', { defaultValue: 'Set status' })}
        className="rounded border bg-background px-1.5 py-0.5 disabled:opacity-50"
      >
        <option value="">{t('panels.scene-browser.bulk.setStatus', { defaultValue: 'Set status…' })}</option>
        {BULK_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
      </select>
      {/* Retarget words (spec 22 §GUI): commit on Enter/blur; empty or non-positive is ignored. */}
      <input
        type="number" min={1} data-testid="scene-browser-bulk-words" disabled={busy}
        placeholder={t('panels.scene-browser.bulk.words', { defaultValue: 'Target words' })}
        onKeyDown={(e) => { if (e.key === 'Enter') commitWords(e); }}
        onBlur={commitWords}
        aria-label={t('panels.scene-browser.bulk.words', { defaultValue: 'Set target words' })}
        className="w-24 rounded border bg-background px-1.5 py-0.5 disabled:opacity-50"
      />
      <button
        type="button" data-testid="scene-browser-bulk-trash" disabled={busy} onClick={onTrash}
        className="inline-flex items-center gap-1 rounded border px-2 py-0.5 text-destructive hover:bg-destructive/10 disabled:opacity-50"
      >
        <Trash2 className="h-3.5 w-3.5" /> {t('panels.scene-browser.bulk.trash', { defaultValue: 'Trash' })}
      </button>
      <button type="button" data-testid="scene-browser-bulk-clear" onClick={onClear} className="text-muted-foreground hover:text-foreground">
        {t('panels.scene-browser.bulk.clear', { defaultValue: 'Clear' })}
      </button>
    </div>
  );
}

// The partial-failure tally. Rendered as its OWN banner, gated on `result != null` — NOT inside the
// selection-gated BulkBar (review HIGH: runBulk sets result AND clears the selection in one commit,
// so a result placed inside the bar unmounts the instant it is set — the honest tally was invisible).
// It survives until the next toggle/setMany/clear, which all null the result in the hook.
function BulkResult({ result, onDismiss, t }: {
  result: BulkResult; onDismiss: () => void; t: (k: string, o?: Record<string, unknown>) => string;
}) {
  const noise = result.conflicts || result.failed;
  return (
    <div
      data-testid="scene-browser-bulk-result"
      className={cn('flex items-center gap-2 border-b px-3 py-1.5 text-xs', noise ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300' : 'bg-primary/5 text-muted-foreground')}
    >
      <span>{[
        t('panels.scene-browser.bulk.updated', { defaultValue: '{{n}} updated', n: result.ok }),
        result.conflicts ? t('panels.scene-browser.bulk.conflicted', { defaultValue: '{{n}} conflicted', n: result.conflicts }) : null,
        result.failed ? t('panels.scene-browser.bulk.failed', { defaultValue: '{{n}} failed', n: result.failed }) : null,
      ].filter(Boolean).join(' · ')}</span>
      <button type="button" data-testid="scene-browser-bulk-result-dismiss" onClick={onDismiss} className="ml-auto hover:text-foreground">×</button>
    </div>
  );
}

function rowTitle(r: SceneUnionRow): string {
  // Prefer the authored intent title; fall back to the parsed heading; else a placeholder.
  return r.spec?.title?.trim() || r.index?.title?.trim() || '(untitled scene)';
}

export function SceneBrowserPanel(props: IDockviewPanelProps) {
  useStudioPanel('scene-browser', props.api);
  const { t } = useTranslation('studio');
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const bookId = host.bookId ?? null;
  const sb = useSceneBrowser(bookId);
  const conf = useConformanceStatus(bookId); // 26 IX-14 — per-chapter dirty (canon-moved) chips
  const bulk = useSceneBulk(accessToken ?? null, sb.reload); // 22-C2b — bulk triage over spec rows

  // Only spec-backed rows carry an editable outline_node → only they are bulk-selectable.
  const specRows = sb.rows.filter((r) => r.spec);
  const selectedTargets = specRows
    .filter((r) => bulk.selected.has(r.spec!.id))
    .map((r) => ({ id: r.spec!.id, version: r.spec!.version }));
  const allSelected = specRows.length > 0 && specRows.every((r) => bulk.selected.has(r.spec!.id));

  if (!bookId) {
    return (
      <div data-testid="studio-scene-browser-panel" className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {t('panels.scene-browser.noBook', { defaultValue: 'Open a book to browse its scenes.' })}
      </div>
    );
  }

  return (
    <div data-testid="studio-scene-browser-panel" className="flex h-full min-h-0 flex-col">
      {/* Toolbar: text search + a live count. */}
      <div className="flex items-center gap-2 border-b p-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            data-testid="scene-browser-search"
            type="text"
            value={sb.query}
            onChange={(e) => sb.setQuery(e.target.value)}
            placeholder={t('panels.scene-browser.search', { defaultValue: 'Search titles & prose…' })}
            className="w-full rounded-md border bg-background py-1 pl-7 pr-2 text-xs"
          />
        </div>
        <span data-testid="scene-browser-count" className="shrink-0 text-xs text-muted-foreground">
          {t('panels.scene-browser.count', { defaultValue: '{{n}} scenes', n: sb.rows.length })}
        </span>
      </div>

      {/* 22-C2b — bulk-action bar. Gated on the ACTIONABLE (visible + selected) targets, not the raw
          selection size, so it never claims more scenes than an apply will actually touch (a selection
          made before a search filtered some rows out stays in the Set but drops out of the count). */}
      {selectedTargets.length > 0 && (
        <BulkBar
          count={selectedTargets.length} busy={bulk.busy}
          onStatus={(s) => void bulk.apply(selectedTargets, { status: s })}
          onWords={(n) => void bulk.apply(selectedTargets, { target_words: n })}
          onTrash={() => void bulk.trash(selectedTargets)}
          onClear={bulk.clear} t={t}
        />
      )}
      {/* Partial-failure tally — independent of the selection (which runBulk clears on completion). */}
      {bulk.result && <BulkResult result={bulk.result} onDismiss={bulk.clear} t={t} />}

      {/* Work-less state (§GUI ②): identity renders; intent is greyed with a create-plan CTA. */}
      {sb.workless && (
        <div
          data-testid="scene-browser-workless"
          className="flex items-center gap-2 border-b bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300"
        >
          <FileWarning className="h-4 w-4 shrink-0" />
          <span className="flex-1">
            {t('panels.scene-browser.workless', {
              defaultValue: 'No plan yet — scene intent (status, POV, tension) is unavailable until you create a plan for this book.',
            })}
          </span>
        </div>
      )}

      {/* Intent side unreachable (composition down) — identity rows still render (soft, not blocking). */}
      {sb.intentUnavailable && !sb.workless && (
        <div
          data-testid="scene-browser-intent-unavailable"
          className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
        >
          <FileWarning className="h-4 w-4 shrink-0" />
          <span className="flex-1">
            {t('panels.scene-browser.intentUnavailable', {
              defaultValue: 'Scene plan is temporarily unavailable — showing the written prose only.',
            })}
          </span>
        </div>
      )}

      {sb.error && (
        <div data-testid="scene-browser-error" className="border-b bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {sb.error}
        </div>
      )}

      {/* The union table. */}
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 bg-background">
            <tr className="border-b text-left text-muted-foreground">
              <th className="w-8 px-2 py-1.5">
                {/* select-all toggles every spec-backed row currently shown (only they are editable) */}
                <input
                  type="checkbox" data-testid="scene-browser-select-all"
                  checked={allSelected} disabled={specRows.length === 0}
                  onChange={(e) => bulk.setMany(specRows.map((r) => r.spec!.id), e.target.checked)}
                  aria-label={t('panels.scene-browser.bulk.selectAll', { defaultValue: 'Select all' })}
                />
              </th>
              <th className="px-2 py-1.5 font-medium">{t('panels.scene-browser.col.num', { defaultValue: '#' })}</th>
              <th className="px-2 py-1.5 font-medium">{t('panels.scene-browser.col.scene', { defaultValue: 'Scene' })}</th>
              <th className="px-2 py-1.5 font-medium">{t('panels.scene-browser.col.status', { defaultValue: 'Status' })}</th>
              <th className="px-2 py-1.5 font-medium">{t('panels.scene-browser.col.tension', { defaultValue: 'Tension' })}</th>
              <th className="px-2 py-1.5 font-medium">{t('panels.scene-browser.col.words', { defaultValue: 'Words' })}</th>
            </tr>
          </thead>
          <tbody>
            {sb.rows.map((r) => (
              <tr
                key={r.key}
                data-testid="scene-browser-row"
                data-shape={r.shape}
                // A row with a spec node is a detail-over-selection target: click selects the scene
                // (bus) and opens the inspector. An index_only row has no spec to inspect yet.
                onClick={r.spec ? () => {
                  host.publish({ type: 'scene', sceneId: r.spec!.id, chapterId: r.chapterId ?? '' });
                  host.openPanel('scene-inspector', { focus: true });
                } : undefined}
                className={cn('border-b hover:bg-muted/40', r.shape === 'spec_only' && 'italic', r.spec && 'cursor-pointer')}
              >
                <td className="w-8 px-2 py-1.5">
                  {/* Only spec-backed rows are bulk-editable; the checkbox click must not open the inspector. */}
                  {r.spec && (
                    <input
                      type="checkbox" data-testid={`scene-browser-select-${r.spec.id}`}
                      checked={bulk.selected.has(r.spec.id)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => bulk.toggle(r.spec!.id)}
                      // Interpolate the scene title so a screen-reader user can tell rows apart (review a11y).
                      aria-label={t('panels.scene-browser.bulk.selectRow', { defaultValue: 'Select scene: {{title}}', title: rowTitle(r) })}
                    />
                  )}
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 text-muted-foreground">
                  {r.sortOrder != null ? r.sortOrder + 1 : '—'}
                </td>
                <td className="px-2 py-1.5">
                  <div className="flex items-center gap-1.5">
                    {/* provenance / state marker */}
                    {r.shape === 'index_only' && r.anchorLost && (
                      <AlertTriangle
                        data-testid="scene-browser-anchor-lost"
                        className="h-3.5 w-3.5 shrink-0 text-amber-500"
                        aria-label={t('panels.scene-browser.anchorLost', { defaultValue: 'Anchor lost' })}
                      />
                    )}
                    <span className={cn(r.shape === 'index_only' && 'text-muted-foreground')}>{rowTitle(r)}</span>
                    <SceneStateBadge row={r} t={t} />
                    {/* 26 IX-14 — canon moved since the last conformance run (amber, advisory). */}
                    {r.chapterId && conf.dirtyChapters.has(r.chapterId) && (
                      <span
                        data-testid="scene-browser-dirty"
                        title={t('panels.scene-browser.dirtyTitle', { defaultValue: 'Canon moved since the last conformance run' })}
                        className="rounded bg-amber-500/15 px-1 py-0.5 text-[10px] text-amber-700 dark:text-amber-300"
                      >
                        {t('panels.scene-browser.dirty', { defaultValue: 'canon moved' })}
                      </span>
                    )}
                  </div>
                </td>
                {/* Intent columns grey out for index_only (no spec) rows. */}
                <td className={cn('px-2 py-1.5', !r.spec && 'text-muted-foreground/50')}>
                  {r.spec ? STATUS_LABEL[r.spec.status] ?? r.spec.status : '—'}
                </td>
                <td className={cn('px-2 py-1.5', !r.spec && 'text-muted-foreground/50')}>
                  {r.spec?.tension != null ? r.spec.tension : '—'}
                </td>
                <td className={cn('px-2 py-1.5', !r.spec && 'text-muted-foreground/50')}>
                  {r.spec?.target_words != null ? r.spec.target_words : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Loading until resolution+first load settle — avoids an empty-state flash for the whole RTT. */}
        {!sb.ready && (
          <div data-testid="scene-browser-loading" className="p-6 text-center text-sm text-muted-foreground">
            {t('panels.scene-browser.loading', { defaultValue: 'Loading…' })}
          </div>
        )}
        {sb.ready && !sb.loading && sb.rows.length === 0 && (
          <div data-testid="scene-browser-empty" className="p-6 text-center text-sm text-muted-foreground">
            {t('panels.scene-browser.empty', { defaultValue: 'No scenes match.' })}
          </div>
        )}
        {sb.hasMore && (
          <div className="p-2 text-center">
            <button
              type="button"
              data-testid="scene-browser-load-more"
              onClick={sb.loadMore}
              disabled={sb.loading}
              className="rounded-md border px-3 py-1 text-xs hover:bg-muted disabled:opacity-50"
            >
              {sb.loading
                ? t('panels.scene-browser.loading', { defaultValue: 'Loading…' })
                : t('panels.scene-browser.loadMore', { defaultValue: 'Load more' })}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function SceneStateBadge({ row, t }: { row: SceneUnionRow; t: (k: string, o?: Record<string, unknown>) => string }) {
  if (row.shape === 'spec_only') {
    return (
      <span data-testid="scene-badge-spec-only" className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
        {t('panels.scene-browser.badge.notWritten', { defaultValue: 'not yet written' })}
      </span>
    );
  }
  if (row.shape === 'index_only') {
    return (
      <span data-testid="scene-badge-index-only" className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
        {row.anchorLost
          ? t('panels.scene-browser.badge.anchorLost', { defaultValue: 'anchor lost' })
          : t('panels.scene-browser.badge.notPlanned', { defaultValue: 'not planned' })}
      </span>
    );
  }
  return null;
}
