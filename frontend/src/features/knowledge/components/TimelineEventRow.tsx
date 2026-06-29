import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Pencil, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TimelineEvent } from '../api';
import { useArchiveEvent } from '../hooks/useEventMutations';
import { EventEditDialog } from './EventEditDialog';

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

// C14 — importance badge. Renders ONLY for the non-null major/pivotal
// events (ordinary events carry importance=null and get no badge — the
// rail must highlight the few that matter, not paint everything). Pivotal
// is the stronger signal so it gets the filled/primary treatment; major
// is the lighter outline. Keyed off the closed BE enum (major|pivotal).
function ImportanceBadge({
  importance,
  label,
}: {
  importance: 'major' | 'pivotal';
  label: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded-full px-1.5 py-[1px] text-[10px] font-medium uppercase tracking-wide',
        importance === 'pivotal'
          ? 'bg-primary text-primary-foreground'
          : 'border border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400',
      )}
      data-testid="timeline-importance-badge"
      data-importance={importance}
    >
      {label}
    </span>
  );
}

function formatConfidence(c: number): string {
  // Clamp to [0, 100] so a bad data import (e.g. confidence=-0.1 or 1.3)
  // surfaces as 0% / 100% in the UI instead of -10% / 130%. BE validation
  // should make this unreachable; defense-in-depth for data drift.
  const pct = Math.round(c * 100);
  return `${Math.max(0, Math.min(100, pct))}%`;
}

// KG-TL — a subtle, accessible "shown in source language" marker. Rendered next
// to any fragment whose `*_translated` flag is false so a reader who picked a
// translation knows the text is source-language (translation pending / absent),
// never a silent mix (AC-T1). Both a sighted badge AND a screen-reader label.
function SourceMarker({ label }: { label: string }) {
  return (
    <sup
      className="ml-0.5 cursor-help select-none text-[8px] font-medium uppercase tracking-wide text-muted-foreground/70"
      title={label}
      aria-label={label}
      data-testid="timeline-source-marker"
    >
      src
    </sup>
  );
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
  const [showEdit, setShowEdit] = useState(false);

  // Phase B C-FE — archive (user "delete"). Confirm + toast; the hook
  // invalidates the timeline so the row drops out on success.
  const archiveMutation = useArchiveEvent({
    onSuccess: () => toast.success(t('events.archive.success')),
    onError: (err) => toast.error(t('events.archive.failed', { error: err.message })),
  });
  const handleArchive = async () => {
    if (!window.confirm(t('events.archive.confirm'))) return;
    try {
      await archiveMutation.archive({ eventId: event.id });
    } catch {
      // onError toast; swallow handled rejection.
    }
  };

  // KG-TL — localized participants: prefer the reader-language name list when
  // the BE provided one, else the source list. Each slot carries a per-slot
  // translated flag (false ⇒ source-fallback ⇒ mark it). When the BE didn't
  // localize (no reader language), the flags default to all-true so nothing is
  // marked (canonical view, AC-T5). Length+order match `participants`.
  const participantNames =
    event.participants_localized ?? event.participants;
  const participantFlags =
    event.participants_translated ??
    event.participants.map(() => true);
  const participantPairs = participantNames.map((name, i) => ({
    name,
    // A pair is "source" when the BE marked it untranslated. Guard the index
    // in case the flags array drifts in length (defensive — treat as translated).
    translated: participantFlags[i] !== false,
    // Stable key: source name + index (localized names can collide).
    key: `${event.participants[i] ?? name}-${i}`,
  }));
  const visibleParticipants = participantPairs.slice(0, VISIBLE_PARTICIPANTS);
  const hiddenCount = Math.max(
    0,
    participantPairs.length - VISIBLE_PARTICIPANTS,
  );

  // KG-TL — localized free-text fields (COALESCE(cache, source) from the BE).
  // `*_translated === false` ⇒ the value is source text awaiting the on-demand
  // cache fill, so we mark it. Undefined flags (no reader language) ⇒ no marker.
  const titleText = event.title_localized ?? event.title;
  const titleIsSource = event.title_translated === false;
  const summaryText = event.summary_localized ?? event.summary;
  const summaryIsSource = event.summary_translated === false;
  // #12 — surface the in-story time cue ("the next morning") on the COLLAPSED row,
  // not only in the expanded detail, so the timeline reads as a chronology at a
  // glance. Same localization (COALESCE(cache, source)) + source-marker pattern.
  const timeCueText = event.time_cue_localized ?? event.time_cue;
  const timeCueIsSource = event.time_cue_translated === false;

  const sourceMarkerLabel = t('timeline.localization.sourceMarker');

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
          <span className="flex min-w-0 items-center gap-1.5">
            {event.importance && (
              <ImportanceBadge
                importance={event.importance}
                label={t(`timeline.importance.${event.importance}`)}
              />
            )}
            <span
              className="block min-w-0 truncate font-medium"
              title={titleText}
            >
              {titleText}
              {titleIsSource && <SourceMarker label={sourceMarkerLabel} />}
            </span>
          </span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            {timeCueText && (
              <span
                className="inline-flex items-center rounded-full bg-amber-500/10 px-1.5 py-[1px] text-[10px] text-amber-700 dark:text-amber-400"
                data-testid="timeline-row-time-cue"
                title={t('timeline.row.timeLabel')}
              >
                🕒 {timeCueText}
                {timeCueIsSource && <SourceMarker label={sourceMarkerLabel} />}
              </span>
            )}
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
                key={p.key}
                className="inline-flex items-center rounded-full bg-muted px-1.5 py-[1px] text-[10px]"
              >
                {p.name}
                {!p.translated && <SourceMarker label={sourceMarkerLabel} />}
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
              {summaryText ?? t('timeline.detail.noSummary')}
              {summaryText && summaryIsSource && (
                <SourceMarker label={sourceMarkerLabel} />
              )}
            </p>
          </div>
          {participantPairs.length > 0 && (
            <div className="mb-2">
              <span className="mb-1 block text-[11px] uppercase tracking-wide text-muted-foreground">
                {t('timeline.detail.participants')}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {participantPairs.map((p) => (
                  <span
                    key={p.key}
                    className="inline-flex items-center rounded-full bg-muted px-2 py-[1px] text-[11px]"
                  >
                    {p.name}
                    {!p.translated && <SourceMarker label={sourceMarkerLabel} />}
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

          {/* Phase B C-FE — edit / archive this event. In the expanded detail
              so they don't clutter the collapsed row. */}
          <div className="mt-3 flex items-center gap-2 border-t pt-2">
            <button
              type="button"
              onClick={() => setShowEdit(true)}
              className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="timeline-event-edit"
            >
              <Pencil className="h-3 w-3" />
              {t('events.edit.cta')}
            </button>
            <button
              type="button"
              onClick={handleArchive}
              disabled={archiveMutation.isPending}
              className="inline-flex items-center gap-1 rounded-md border border-destructive/40 px-2 py-1 text-[11px] text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="timeline-event-archive"
            >
              <Trash2 className="h-3 w-3" />
              {archiveMutation.isPending ? t('events.archive.archiving') : t('events.archive.cta')}
            </button>
          </div>
        </div>
      )}
      <EventEditDialog open={showEdit} onOpenChange={setShowEdit} event={event} />
    </li>
  );
}
