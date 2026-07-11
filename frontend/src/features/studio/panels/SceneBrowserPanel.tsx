// 22-C2 — the `scene-browser` dock panel: a book-wide table that renders the UNION of the
// book-service scene index and the composition spec (spec 22 §GUI). It reads book-service, not
// outline_node, so an imported book's scenes show even before any composition Work exists (the
// empty-rail bug, fixed at the root). Provenance is colour-ticked: teal = identity (book-service),
// amber = intent (composition). Logic lives in useSceneBrowser; this file only renders.
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { AlertTriangle, FileWarning, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { useSceneBrowser } from './useSceneBrowser';
import type { SceneUnionRow } from './sceneUnion';

const STATUS_LABEL: Record<string, string> = {
  empty: 'Empty', outline: 'Outline', drafting: 'Drafting', done: 'Done',
};

function rowTitle(r: SceneUnionRow): string {
  // Prefer the authored intent title; fall back to the parsed heading; else a placeholder.
  return r.spec?.title?.trim() || r.index?.title?.trim() || '(untitled scene)';
}

export function SceneBrowserPanel(props: IDockviewPanelProps) {
  useStudioPanel('scene-browser', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const bookId = host.bookId ?? null;
  const sb = useSceneBrowser(bookId);

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
