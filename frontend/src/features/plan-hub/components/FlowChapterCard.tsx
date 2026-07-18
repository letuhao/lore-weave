// Plan Hub redesign — one CHAPTER card in a lane (mockup `.ch`). Fixed width so the wrap grid stays
// even; status → fill texture; authorship → serif(authored)/mono(mined) title. Clicking the card
// SELECTS it (→ drawer edit/archive). Scenes load lazily: a chapter's scene branch is fetched only
// when the writer reveals it (the sealed "scenes load only for an expanded chapter" budget), so a card
// starts with a quiet "scenes" toggle rather than auto-fetching scenes for every chapter on the book.
import { memo } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { LaneChapter } from '../layout/laneTree';
import { chapterCardClass, normStatus, statusDotClass } from './flowPresentation';

export interface FlowChapterCardProps {
  chapter: LaneChapter;
  /** The chapter's DISPLAY number (book reading ordinal for a contiguous arc, else within-arc). */
  displayNo: number;
  selected: boolean;
  isHere: boolean;
  /** PH15 find — this card matches the toolbar query (ringed, never filtered). */
  matched: boolean;
  onSelect: (nodeId: string) => void;
  onToggleScenes: (nodeId: string) => void;
  /** Add a scene under this chapter. Null ⇒ no EDIT grant / no Work / no book chapter id. */
  onAddScene: ((chapterNodeId: string, bookChapterId: string) => void) | null;
  addingChild: boolean;
  /** The arc this chapter is currently in (null for an unassigned chapter), so the move picker can
   *  exclude it. */
  currentArcId: string | null;
  /** The arcs a chapter can be MOVED/filed into. Empty ⇒ no move picker. */
  arcOptions: { id: string; title: string; depth: number }[];
  /** Re-file this chapter under another arc (also FILES an unassigned chapter). Null ⇒ no EDIT grant. */
  onMoveToArc: ((chapterNodeId: string, arcId: string) => void) | null;
}

function FlowChapterCardInner({
  chapter, displayNo, selected, isHere, matched, onSelect, onToggleScenes, onAddScene, addingChild,
  currentArcId, arcOptions, onMoveToArc,
}: FlowChapterCardProps) {
  const { t } = useTranslation('studio');
  const status = normStatus(chapter.status);
  const machine = chapter.source === 'mined';
  const canAddScene = onAddScene && chapter.chapterId;
  const moveTargets = onMoveToArc ? arcOptions.filter((a) => a.id !== currentArcId) : [];

  return (
    <div
      data-testid={`flow-ch-${chapter.id}`}
      data-status={status}
      data-source={chapter.source}
      onClick={() => onSelect(chapter.id)}
      className={cn(
        'group relative w-[188px] shrink-0 cursor-pointer rounded-md border px-2.5 py-2 transition-colors hover:border-primary/55',
        chapterCardClass(status),
        selected && 'outline outline-2 outline-primary outline-offset-1',
        isHere && 'outline outline-2 outline-offset-2 outline-sky-500',
        matched && 'ring-2 ring-yellow-500',
      )}
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className={cn('h-[7px] w-[7px] shrink-0 rounded-full', statusDotClass(status))} />
        <span className="font-mono text-[9.5px] text-muted-foreground">
          {t('planHub.flow.chNo', { n: displayNo, defaultValue: 'ch {{n}}' })}
        </span>
        <span className="ml-auto font-mono text-[9px] uppercase tracking-wide text-muted-foreground">
          {t(`planHub.flow.status.${status}`, status)}
        </span>
      </div>
      <div
        className={cn(
          'line-clamp-2 font-semibold leading-snug text-foreground/95',
          machine ? 'font-mono text-[12px]' : 'font-serif text-[13px]',
        )}
        title={chapter.title || undefined}
      >
        {chapter.title || t('planHub.flow.untitledChapter', 'Untitled chapter')}
      </div>

      {chapter.scenesExpanded ? (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {/* collapse the scene branch again (the reveal toggle is gone once open) */}
          <button
            type="button"
            data-testid={`flow-hide-scenes-${chapter.id}`}
            onClick={(e) => { e.stopPropagation(); onToggleScenes(chapter.id); }}
            className="font-mono text-[10px] text-muted-foreground/70 hover:text-primary"
            title={t('planHub.flow.hideScenes', 'Hide scenes')}
          >
            ▾
          </button>
          {chapter.scenes.map((sc) => (
            <span
              key={sc.id}
              data-testid={`flow-sc-${sc.id}`}
              onClick={(e) => { e.stopPropagation(); onSelect(sc.id); }}
              className={cn(
                'max-w-full cursor-pointer truncate rounded border px-1.5 py-0.5 text-[10.5px]',
                sc.source === 'mined'
                  ? 'border-accent/30 bg-accent/15 font-mono text-[10px] text-foreground/90'
                  : 'border-primary/30 bg-primary/15 text-foreground/90',
              )}
              title={sc.title || undefined}
            >
              {sc.title || t('planHub.flow.untitledScene', 'Untitled scene')}
            </span>
          ))}
          {canAddScene && (
            <button
              type="button"
              data-testid={`flow-add-scene-${chapter.id}`}
              disabled={addingChild}
              onClick={(e) => { e.stopPropagation(); onAddScene!(chapter.id, chapter.chapterId!); }}
              className="cursor-pointer rounded border border-dashed border-border bg-transparent px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground/80 hover:border-primary/55 hover:text-primary disabled:opacity-50"
            >
              {t('planHub.flow.addScene', '+ scene')}
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          data-testid={`flow-toggle-scenes-${chapter.id}`}
          onClick={(e) => { e.stopPropagation(); onToggleScenes(chapter.id); }}
          className="mt-2 font-mono text-[10px] text-muted-foreground/70 hover:text-primary"
        >
          {t('planHub.flow.showScenes', '▸ scenes')}
        </button>
      )}

      {/* Move / file this chapter into another arc — the non-drag replacement for the old canvas
          drag-into-lane, and the ONLY way to file an arc-less chapter. Hover-revealed to stay calm. */}
      {moveTargets.length > 0 && (
        <select
          data-testid={`flow-move-${chapter.id}`}
          value=""
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => { e.stopPropagation(); if (e.target.value) onMoveToArc!(chapter.id, e.target.value); }}
          className="mt-1.5 w-full cursor-pointer rounded border border-border bg-transparent px-1 py-0.5 font-mono text-[9px] text-muted-foreground opacity-0 transition-opacity focus:opacity-100 group-hover:opacity-100 disabled:opacity-40"
          disabled={addingChild}
          aria-label={t('planHub.flow.moveTo', 'Move to arc')}
        >
          <option value="">{t('planHub.flow.moveTo', 'move to arc…')}</option>
          {moveTargets.map((a) => (
            <option key={a.id} value={a.id}>{`${'· '.repeat(a.depth)}${a.title || t('planHub.flow.untitledArc', 'Untitled arc')}`}</option>
          ))}
        </select>
      )}
    </div>
  );
}

export const FlowChapterCard = memo(FlowChapterCardInner);
