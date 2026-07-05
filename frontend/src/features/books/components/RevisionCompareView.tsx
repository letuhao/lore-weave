// Revision compare view — pickers + view-mode toggle + the diff. Render-only:
// all logic lives in useRevisionCompare.
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Columns2, AlignJustify } from 'lucide-react';

import { useRevisionCompare } from '@/features/books/hooks/useRevisionCompare';
import { RevisionDiff } from '@/features/books/components/RevisionDiff';
import type { RevisionSummary } from '@/features/books/types';

type Props = {
  token: string | null;
  bookId: string;
  chapterId: string;
  /** #20_agent_mode.md D2 — an initial (left, right) revision pair, e.g. a
   * drafted unit's (pre_revision_id, post_revision_id) from Agent Mode's diff
   * panel. Omitted → defaults to the two newest revisions (unchanged). */
  initialLeftId?: string;
  initialRightId?: string;
  /** The classic route back-link only makes sense when this view lives at its
   * own route (ChapterComparePage). Studio's `chapter-revision-compare` panel
   * never navigates (DOCK-7) so it hides this button instead. */
  showBackLink?: boolean;
};

function revLabel(r: RevisionSummary): string {
  const when = new Date(r.created_at).toLocaleString();
  return r.message ? `${when} — ${r.message}` : when;
}

// Module-level so it isn't re-created each render (which would remount the
// <select> and drop its focus/open state when the compare query resolves).
function Picker({
  label, items, value, onChange, emptyLabel, testid,
}: {
  label: string; items: RevisionSummary[]; value: string;
  onChange: (v: string) => void; emptyLabel: string; testid: string;
}) {
  return (
    <select
      aria-label={label}
      data-testid={testid}
      className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 text-xs"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {items.length === 0 && <option value="">{emptyLabel}</option>}
      {items.map((r) => (
        <option key={r.revision_id} value={r.revision_id}>
          {revLabel(r)}
        </option>
      ))}
    </select>
  );
}

export function RevisionCompareView({
  token, bookId, chapterId, initialLeftId, initialRightId, showBackLink = true,
}: Props) {
  const { t } = useTranslation('editor');
  const navigate = useNavigate();
  const c = useRevisionCompare(token, bookId, chapterId, { leftId: initialLeftId, rightId: initialRightId });
  const emptyLabel = t('compare.no_revisions', { defaultValue: 'No revisions' });

  return (
    <div className="flex h-full flex-col">
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        {showBackLink && (
          <button
            data-testid="compare-back"
            onClick={() => navigate(`/books/${bookId}/chapters/${chapterId}/edit`)}
            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:text-primary"
          >
            <ArrowLeft className="h-3 w-3" /> {t('compare.back', { defaultValue: 'Back to editor' })}
          </button>
        )}
        <h1 className="mr-2 text-sm font-semibold">{t('compare.title', { defaultValue: 'Compare revisions' })}</h1>

        <div className="flex min-w-[420px] flex-1 items-center gap-2">
          <Picker testid="compare-left-select" label={t('compare.left', { defaultValue: 'Left revision' })} items={c.items} value={c.leftId} onChange={c.setLeftId} emptyLabel={emptyLabel} />
          <span className="text-xs text-muted-foreground">vs</span>
          <Picker testid="compare-right-select" label={t('compare.right', { defaultValue: 'Right revision' })} items={c.items} value={c.rightId} onChange={c.setRightId} emptyLabel={emptyLabel} />
          {c.hasMore && (
            <button
              data-testid="compare-load-more"
              onClick={() => void c.loadMore()}
              disabled={c.loadingMore}
              title={t('compare.load_more_hint', { defaultValue: 'Load older revisions into the picker' })}
              className="shrink-0 whitespace-nowrap rounded-md border px-2 py-1 text-xs hover:text-primary disabled:opacity-50"
            >
              {c.loadingMore
                ? t('compare.loading', { defaultValue: 'Loading…' })
                : t('compare.load_more', { defaultValue: 'Load more ({{loaded}}/{{total}})', loaded: c.items.length, total: c.total })}
            </button>
          )}
        </div>

        <div className="inline-flex overflow-hidden rounded-md border">
          <button
            data-testid="compare-mode-sxs"
            aria-label={t('compare.side_by_side', { defaultValue: 'Side by side' })}
            onClick={() => c.setViewMode('side-by-side')}
            className={`inline-flex items-center gap-1 px-2 py-1 text-xs ${c.viewMode === 'side-by-side' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
          >
            <Columns2 className="h-3 w-3" /> {t('compare.side_by_side', { defaultValue: 'Side by side' })}
          </button>
          <button
            data-testid="compare-mode-inline"
            aria-label={t('compare.inline', { defaultValue: 'Inline' })}
            onClick={() => c.setViewMode('inline')}
            className={`inline-flex items-center gap-1 px-2 py-1 text-xs ${c.viewMode === 'inline' ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
          >
            <AlignJustify className="h-3 w-3" /> {t('compare.inline', { defaultValue: 'Inline' })}
          </button>
        </div>
      </div>

      {/* body */}
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {c.revisions.isLoading && <p className="text-xs text-muted-foreground">{t('compare.loading', { defaultValue: 'Loading…' })}</p>}
        {c.items.length < 2 && !c.revisions.isLoading && (
          <p data-testid="compare-need-two" className="text-xs text-muted-foreground">{t('compare.need_two', { defaultValue: 'This chapter needs at least two saved revisions to compare.' })}</p>
        )}
        {c.compare.isError && <p className="text-xs text-destructive">{t('compare.error', { defaultValue: 'Could not load the comparison.' })}</p>}
        {c.compare.isLoading && c.items.length >= 2 && (
          <p className="text-xs text-muted-foreground">{t('compare.diffing', { defaultValue: 'Computing diff…' })}</p>
        )}
        {c.compare.data && (
          <div className="flex flex-col gap-2">
            {c.compare.data.truncated && (
              <p data-testid="compare-truncated" className="rounded-md bg-amber-50 px-2 py-1 text-[11px] text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                {t('compare.truncated', { defaultValue: 'These revisions are very large — showing a full replace instead of a fine-grained diff.' })}
              </p>
            )}
            {c.leftId === c.rightId && (
              <p data-testid="compare-same" className="text-[11px] text-muted-foreground">{t('compare.same', { defaultValue: 'Both sides are the same revision — no differences.' })}</p>
            )}
            <RevisionDiff diff={c.compare.data.diff} mode={c.viewMode} />
          </div>
        )}
      </div>
    </div>
  );
}
