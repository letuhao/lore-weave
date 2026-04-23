import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { TimelineEvent } from '../api';

// K19e.1 — presentational row for a :Event. Click / Enter / Space
// toggles expansion via the parent tab's `selectedEventId` state.
// Expansion reveals summary + all participants + source_types in-line;
// there's no detail panel because the list response already carries
// the full Event body (BE ships no dedicated detail endpoint).
//
// a11y: row is a <button> semantically (role="button" + tabIndex).
// Keyboard users get Enter/Space activation matching the K19d β
// EntitiesTable pattern. `aria-expanded` reflects the toggle state
// for screen-reader users.

export interface TimelineEventRowProps {
  event: TimelineEvent;
  isExpanded: boolean;
  onToggle: () => void;
}

const VISIBLE_PARTICIPANTS = 3;

function formatConfidence(c: number): string {
  // Clamp to [0, 100] so a bad data import (e.g. confidence=-0.1 or 1.3)
  // surfaces as 0% / 100% in the UI instead of -10% / 130%. BE validation
  // should make this unreachable; defense-in-depth for data drift.
  const pct = Math.round(c * 100);
  return `${Math.max(0, Math.min(100, pct))}%`;
}

function chapterShort(chapterId: string | null): string {
  if (!chapterId) return '';
  // Short suffix of the chapter UUID so the user has *something* to
  // distinguish chapters with. C6 (D-K19e-β-01) now denormalizes the
  // real title in via `event.chapter_title`; this fallback stays for
  // the graceful-degrade path when book-service was unavailable OR
  // the chapter was trashed after the event was written.
  return chapterId.length > 8 ? `…${chapterId.slice(-8)}` : chapterId;
}

export function TimelineEventRow({
  event,
  isExpanded,
  onToggle,
}: TimelineEventRowProps) {
  const { t } = useTranslation('knowledge');

  const visibleParticipants = event.participants.slice(0, VISIBLE_PARTICIPANTS);
  const hiddenCount = Math.max(
    0,
    event.participants.length - VISIBLE_PARTICIPANTS,
  );
  // C6 (D-K19e-β-01) — prefer the BE-resolved chapter title over the
  // UUID-suffix fallback. Either both are empty (no chapter on this
  // event) or we render exactly one.
  const chapterLabel = event.chapter_title ?? chapterShort(event.chapter_id);

  return (
    <li>
      <button
        type="button"
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded ? 'true' : 'false'}
        onClick={onToggle}
        onKeyDown={(ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            onToggle();
          }
        }}
        className={cn(
          'grid w-full grid-cols-[56px_1fr_auto] items-start gap-3 px-3 py-2.5 text-left text-[12px] transition-colors hover:bg-muted/50',
          isExpanded && 'bg-primary/5 ring-1 ring-primary/30',
        )}
        data-testid="timeline-event-row"
        data-event-id={event.id}
      >
        <span
          className="pt-[2px] text-right font-mono text-[11px] text-muted-foreground tabular-nums"
          title={t('timeline.row.orderLabel')}
        >
          {event.event_order ?? t('timeline.row.noOrder')}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium" title={event.title}>
            {event.title}
          </span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            {chapterLabel && (
              <span className="inline-flex items-center">
                {t('timeline.row.chapterLabel')}:{' '}
                {event.chapter_title ? (
                  // Real title — render as plain text so it reads as
                  // prose. The UUID short keeps its monospace <code>
                  // styling below as a fallback visual signal that
                  // the title was unavailable.
                  <span className="ml-1">{chapterLabel}</span>
                ) : (
                  // /review-impl L4: screen readers announce <code>
                  // content character-by-character ("c-c-c dash
                  // d-d-d-d"). aria-label overrides that with prose
                  // indicating the UUID is a fallback reference,
                  // not a real title. Visual monospace is preserved
                  // for sighted users as the "fallback" signal.
                  <code
                    className="ml-1"
                    aria-label={t('timeline.row.chapterUnresolved', {
                      id: chapterLabel,
                    })}
                  >
                    {chapterLabel}
                  </code>
                )}
              </span>
            )}
            {visibleParticipants.map((p) => (
              <span
                key={p}
                className="inline-flex items-center rounded-full bg-muted px-1.5 py-[1px] text-[10px]"
              >
                {p}
              </span>
            ))}
            {hiddenCount > 0 && (
              <span className="text-[10px]">
                {t('timeline.row.participantsMore', { count: hiddenCount })}
              </span>
            )}
          </span>
        </span>
        <span
          className="pt-[2px] text-right text-[11px] text-muted-foreground tabular-nums"
          title={t('timeline.row.confidenceLabel')}
        >
          {formatConfidence(event.confidence)}
        </span>
      </button>

      {isExpanded && (
        <div
          className="border-t bg-muted/30 px-3 py-2.5 text-[12px]"
          data-testid="timeline-event-detail"
        >
          <div className="mb-2">
            <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">
              {t('timeline.detail.summary')}
            </span>
            <p className="whitespace-pre-wrap text-foreground">
              {event.summary ?? t('timeline.detail.noSummary')}
            </p>
          </div>
          {event.participants.length > 0 && (
            <div className="mb-2">
              <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">
                {t('timeline.detail.participants')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {event.participants.map((p) => (
                  <span
                    key={p}
                    className="inline-flex items-center rounded-full bg-muted px-2 py-[1px] text-[11px]"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
          {event.source_types.length > 0 && (
            <div>
              <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">
                {t('timeline.detail.sources')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {event.source_types.map((s) => (
                  <span
                    key={s}
                    className="inline-flex items-center rounded-full border px-2 py-[1px] text-[11px]"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
