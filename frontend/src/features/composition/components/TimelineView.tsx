// LOOM Composition (T2.3) — Timeline: a spoiler-safe horizontal chronology of the
// book's :Event nodes. Pick an entity / date range to narrow it; the amber "AI sees
// ≤ here" marker shows the current chapter's spoiler cutoff (events past it dimmed);
// "Hide spoilers" drops them entirely. Click an event → open its chapter. Hand-rolled
// SVG (PO decision, consistent with the T1.3/T2.2 graph canvases). Render-only; logic
// in useTimeline.
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { TIMELINE_LIMIT, axisX, useTimeline, visibleOnPage } from '../hooks/useTimeline';
import { SpoilerCutMarker } from './SpoilerCutMarker';
import { TimelineEventPoint } from './TimelineEventPoint';

const PAD = 40;
const MIN_SPACING = 96;
const AXIS_Y = 96;
const SVG_H = 184;
const BASE_W = 640;

export function TimelineView({ bookId, chapterId, token }: { bookId: string; chapterId: string; token: string | null }) {
  const { t } = useTranslation('composition');
  const navigate = useNavigate();
  const tl = useTimeline(bookId, chapterId, token);

  const count = tl.events.length;
  const width = Math.max(BASE_W, count * MIN_SPACING + 2 * PAD);
  const vop = visibleOnPage(tl.offset, count, tl.visibleCount);
  const pointGap = count > 1 ? (width - 2 * PAD) / (count - 1) : MIN_SPACING;
  // Marker x = midway across the visible/hidden boundary (clamped at the ends).
  const markerX = useMemo(() => {
    if (count === 0) return PAD;
    if (vop <= 0) return Math.max(8, axisX(0, count, width, PAD) - pointGap / 2);
    if (vop >= count) return axisX(count - 1, count, width, PAD) + pointGap / 2;
    return (axisX(vop - 1, count, width, PAD) + axisX(vop, count, width, PAD)) / 2;
  }, [vop, count, width, pointGap]);

  // The cutoff marker belongs ONLY on the page whose global index range actually
  // straddles the visible/hidden boundary — else a multi-page book shows a spurious
  // "AI sees ≤ here" on every page (markerX would clamp to a page edge). Per-event
  // dimming (i >= vop) stays correct on every page regardless.
  const showCut = tl.visibleCount != null && tl.visibleCount >= tl.offset && tl.visibleCount <= tl.offset + count;

  const openChapter = (cid: string) => navigate(`/books/${bookId}/chapters/${cid}/edit`);
  const totalPages = Math.max(1, Math.ceil(tl.total / TIMELINE_LIMIT));

  return (
    <div className="flex h-full flex-col" data-testid="composition-timeline">
      {/* filter bar */}
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="text-muted-foreground">{t('chrono.title', { defaultValue: 'Timeline' })}</span>
        <select
          data-testid="timeline-entity-select"
          aria-label={t('chrono.filter_entity', { defaultValue: 'Filter by entity' })}
          className="max-w-[10rem] rounded border bg-background px-1 py-0.5"
          value={tl.entityId ?? ''}
          onChange={(e) => tl.setEntityId(e.target.value || null)}
        >
          <option value="">{t('chrono.all_entities', { defaultValue: 'All entities' })}</option>
          {tl.entities.map((en) => <option key={en.id} value={en.id}>{en.name}</option>)}
        </select>
        <input
          data-testid="timeline-date-from"
          aria-label={t('chrono.filter_date_from', { defaultValue: 'From date (YYYY-MM-DD)' })}
          placeholder={t('chrono.date_from_ph', { defaultValue: 'from' })}
          className="w-20 rounded border bg-background px-1 py-0.5"
          value={tl.dateFrom ?? ''}
          onChange={(e) => tl.setDateRange(e.target.value || null, tl.dateTo)}
        />
        <input
          data-testid="timeline-date-to"
          aria-label={t('chrono.filter_date_to', { defaultValue: 'To date (YYYY-MM-DD)' })}
          placeholder={t('chrono.date_to_ph', { defaultValue: 'to' })}
          className="w-20 rounded border bg-background px-1 py-0.5"
          value={tl.dateTo ?? ''}
          onChange={(e) => tl.setDateRange(tl.dateFrom, e.target.value || null)}
        />
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            data-testid="timeline-hide-spoilers"
            checked={tl.hideSpoilers}
            onChange={(e) => tl.setHideSpoilers(e.target.checked)}
          />
          <span className="text-muted-foreground/80">{t('chrono.hide_spoilers', { defaultValue: 'Hide spoilers' })}</span>
        </label>
      </div>

      {/* body */}
      {tl.projectLoading || tl.isLoading ? (
        <Hint>{t('chrono.loading', { defaultValue: 'Loading timeline…' })}</Hint>
      ) : tl.rangeError ? (
        <Hint testid="timeline-range-error">
          {t('chrono.range_error', { defaultValue: 'Check the date range — the start must be on or before the end.' })}
        </Hint>
      ) : !tl.projectId ? (
        <Hint>{t('chrono.noProject', { defaultValue: 'No knowledge graph yet — extract this book to build the timeline.' })}</Hint>
      ) : count === 0 ? (
        <Hint testid="timeline-empty">{t('chrono.empty', { defaultValue: 'No events yet — extract this book first.' })}</Hint>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <svg
            data-testid="timeline-svg"
            width={width}
            height={SVG_H}
            role="list"
            aria-label={t('chrono.title', { defaultValue: 'Timeline' })}
          >
            <line x1={PAD} y1={AXIS_Y} x2={width - PAD} y2={AXIS_Y} className="stroke-border" strokeWidth={2} />
            {showCut && <SpoilerCutMarker x={markerX} top={28} bottom={SVG_H - 28} />}
            {tl.events.map((ev, i) => (
              <TimelineEventPoint
                key={ev.id}
                event={ev}
                x={axisX(i, count, width, PAD)}
                axisY={AXIS_Y}
                hidden={i >= vop}
                labelBelow={i % 2 === 1}
                onOpen={openChapter}
              />
            ))}
          </svg>
        </div>
      )}

      {/* pagination */}
      {tl.total > TIMELINE_LIMIT && !tl.rangeError && !!tl.projectId && (
        <div className="flex flex-shrink-0 items-center justify-center gap-3 border-t px-3 py-1 text-[11px]">
          <button
            data-testid="timeline-prev"
            disabled={tl.page === 0}
            className="rounded border px-2 py-0.5 disabled:opacity-40"
            onClick={() => tl.setPage(tl.page - 1)}
          >
            {t('chrono.prev', { defaultValue: 'Prev' })}
          </button>
          <span className="text-muted-foreground">
            {t('chrono.page', { defaultValue: '{{page}} / {{total}}', page: tl.page + 1, total: totalPages })}
          </span>
          <button
            data-testid="timeline-next"
            disabled={tl.page + 1 >= totalPages}
            className="rounded border px-2 py-0.5 disabled:opacity-40"
            onClick={() => tl.setPage(tl.page + 1)}
          >
            {t('chrono.next', { defaultValue: 'Next' })}
          </button>
        </div>
      )}
    </div>
  );
}

function Hint({ children, testid }: { children: React.ReactNode; testid?: string }) {
  return <div data-testid={testid} className="p-3 text-xs text-muted-foreground">{children}</div>;
}
