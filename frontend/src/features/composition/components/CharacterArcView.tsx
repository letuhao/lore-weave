// LOOM Composition (T2.4) — Character Arc: one character's events in event_order on
// a compact arc (spoiler-cut at the current chapter), an active→gone state band, and
// the current 1-hop relations strip. Reuses T2.3's TimelineEventPoint / SpoilerCutMarker
// / axisX / visibleOnPage (decoupled cutoff, no FE stride). Render-only; logic in
// useCharacterArc. Controlled entity (lifted to CompositionPanel so the Cast codex can
// launch this view with a character preselected).
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { EventEditDialog } from '@/features/knowledge/components/EventEditDialog';
import { axisX, visibleOnPage } from '../hooks/useTimeline';
import { arcBandSplit, useCharacterArc } from '../hooks/useCharacterArc';
import { TimelineEventPoint } from './TimelineEventPoint';
import { SpoilerCutMarker } from './SpoilerCutMarker';
import { ArcRelationsStrip } from './ArcRelationsStrip';

const PAD = 40;
const MIN_SPACING = 110;
const AXIS_Y = 84;
const SVG_H = 140;
const BASE_W = 560;
const BAND_Y = 20;
const BAND_H = 6;

export function CharacterArcView({
  bookId, chapterId, token, entityId, onEntityChange,
}: {
  bookId: string;
  chapterId: string;
  token: string | null;
  entityId: string | null;
  onEntityChange: (id: string) => void;
}) {
  const { t } = useTranslation('composition');
  const navigate = useNavigate();
  const arc = useCharacterArc(bookId, chapterId, token, entityId);
  const [addOpen, setAddOpen] = useState(false);

  const count = arc.events.length;
  const width = Math.max(BASE_W, count * MIN_SPACING + 2 * PAD);
  const vop = visibleOnPage(0, count, arc.visibleCount); // single page (offset 0)
  // Boundary x = midway between the two straddling points (clamped to the pads).
  const boundaryX = (split: number) => {
    if (count === 0 || split <= 0) return PAD;
    if (split >= count) return width - PAD;
    return (axisX(split - 1, count, width, PAD) + axisX(split, count, width, PAD)) / 2;
  };
  // Cutoff marker only when the visible/hidden boundary lands within the page.
  const showCut = arc.visibleCount != null && arc.visibleCount <= count;
  const markerX = useMemo(() => boundaryX(vop), [vop, count, width]); // eslint-disable-line react-hooks/exhaustive-deps

  const bandSplit = arcBandSplit(arc.events, arc.state?.status, arc.state?.from_order);
  const bandX = boundaryX(bandSplit);

  const rosterName = (id: string) => arc.roster.find((e) => e.id === id)?.name ?? id;
  // T2.2 lesson: a controlled <select value=> needs its value to be an option, else
  // it blanks. A Cast-launched entity past the 200-cap roster won't be listed — surface it.
  const pickerOptions = useMemo(() => {
    const opts = arc.roster.map((e) => ({ id: e.id, name: e.name }));
    if (arc.effectiveEntityId && !opts.some((o) => o.id === arc.effectiveEntityId)) {
      opts.unshift({ id: arc.effectiveEntityId, name: arc.focusName ?? rosterName(arc.effectiveEntityId) });
    }
    return opts;
  }, [arc.roster, arc.effectiveEntityId, arc.focusName]); // eslint-disable-line react-hooks/exhaustive-deps

  const gone = arc.state?.status === 'gone';
  const openChapter = (cid: string) => navigate(`/books/${bookId}/chapters/${cid}/edit`);

  return (
    <div className="flex h-full flex-col" data-testid="composition-arc">
      {/* header: picker + state badge */}
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="text-muted-foreground">{t('chararc.title', { defaultValue: 'Character Arc' })}</span>
        <select
          data-testid="arc-character-select"
          aria-label={t('chararc.pick_character', { defaultValue: 'Pick a character' })}
          className="max-w-[10rem] rounded border bg-background px-1 py-0.5"
          value={arc.effectiveEntityId ?? ''}
          onChange={(e) => onEntityChange(e.target.value)}
        >
          {pickerOptions.length === 0 && <option value="">{t('chararc.pick_character', { defaultValue: 'Pick a character' })}</option>}
          {pickerOptions.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        {arc.state?.status && (
          <span
            data-testid="arc-state-badge"
            data-status={gone ? 'gone' : 'active'}
            className={'rounded px-1.5 py-0.5 text-[10px] ' + (gone ? 'bg-rose-500/15 text-rose-600 dark:text-rose-400' : 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400')}
          >
            {gone ? t('chararc.gone', { defaultValue: 'gone' }) : t('chararc.active', { defaultValue: 'active' })}
          </span>
        )}
        {/* + Add event — author a new timeline event onto THIS character's arc
            (D-KG-EVENT-CREATE-ROUTE). Needs a project + a resolved character so
            the new event's participant list anchors it to the arc. */}
        {arc.projectId && arc.effectiveEntityId && (
          <button
            type="button"
            data-testid="arc-add-event"
            className="ml-auto inline-flex items-center gap-1 rounded border px-1.5 py-0.5 hover:bg-accent/50"
            onClick={() => setAddOpen(true)}
          >
            <Plus className="h-3 w-3" />
            {t('chararc.addEvent', { defaultValue: '+ Add event' })}
          </button>
        )}
      </div>

      {/* body */}
      {arc.projectLoading || arc.isLoading ? (
        <Hint>{t('chararc.loading', { defaultValue: 'Loading character arc…' })}</Hint>
      ) : !arc.projectId || arc.roster.length === 0 ? (
        <Hint>{t('chararc.noProject', { defaultValue: 'No knowledge graph yet — extract this book to chart character arcs.' })}</Hint>
      ) : count === 0 ? (
        <Hint testid="arc-empty">{t('chararc.empty', { defaultValue: 'This character has no events yet.' })}</Hint>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-auto">
            <svg data-testid="arc-svg" width={width} height={SVG_H} role="list" aria-label={t('chararc.title', { defaultValue: 'Character Arc' })}>
              {/* active→gone state band */}
              {arc.state?.status && (
                <g data-testid="arc-band">
                  <rect data-testid="arc-band-active" x={PAD} y={BAND_Y} width={Math.max(0, bandX - PAD)} height={BAND_H} rx={3} className="fill-emerald-500/30" />
                  {bandSplit < count && (
                    <rect data-testid="arc-band-gone" x={bandX} y={BAND_Y} width={Math.max(0, width - PAD - bandX)} height={BAND_H} rx={3} className="fill-rose-500/30" />
                  )}
                </g>
              )}
              <line x1={PAD} y1={AXIS_Y} x2={width - PAD} y2={AXIS_Y} className="stroke-border" strokeWidth={2} />
              {showCut && <SpoilerCutMarker x={markerX} top={BAND_Y + BAND_H + 4} bottom={SVG_H - 24} />}
              {arc.events.map((ev, i) => (
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
          <div className="flex-shrink-0 border-t">
            <ArcRelationsStrip entityId={arc.effectiveEntityId!} relations={arc.relations} />
          </div>
        </div>
      )}

      {arc.projectId && arc.effectiveEntityId && (
        <EventEditDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          create={{
            projectId: arc.projectId,
            chapterId: chapterId || null,
            // Anchor the new event to THIS character (its display name) so it
            // lands on the arc's entity-scoped timeline.
            participants: [arc.focusName ?? rosterName(arc.effectiveEntityId)],
          }}
        />
      )}
    </div>
  );
}

function Hint({ children, testid }: { children: React.ReactNode; testid?: string }) {
  return <div data-testid={testid} className="p-3 text-xs text-muted-foreground">{children}</div>;
}
