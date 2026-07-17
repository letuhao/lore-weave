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
  index: number;
  selected: boolean;
  isHere: boolean;
  /** PH15 find — this card matches the toolbar query (ringed, never filtered). */
  matched: boolean;
  onSelect: (nodeId: string) => void;
  onToggleScenes: (nodeId: string) => void;
  /** Add a scene under this chapter. Null ⇒ no EDIT grant / no Work / no book chapter id. */
  onAddScene: ((chapterNodeId: string, bookChapterId: string) => void) | null;
  addingChild: boolean;
}

function FlowChapterCardInner({
  chapter, index, selected, isHere, matched, onSelect, onToggleScenes, onAddScene, addingChild,
}: FlowChapterCardProps) {
  const { t } = useTranslation('studio');
  const status = normStatus(chapter.status);
  const machine = chapter.source === 'mined';
  const canAddScene = onAddScene && chapter.chapterId;

  return (
    <div
      data-testid={`flow-ch-${chapter.id}`}
      data-status={status}
      data-source={chapter.source}
      onClick={() => onSelect(chapter.id)}
      className={cn(
        'relative w-[188px] shrink-0 cursor-pointer rounded-md border px-2.5 py-2 transition-colors hover:border-primary/55',
        chapterCardClass(status),
        selected && 'outline outline-2 outline-primary outline-offset-1',
        isHere && 'outline outline-2 outline-offset-2 outline-sky-500',
        matched && 'ring-2 ring-yellow-500',
      )}
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className={cn('h-[7px] w-[7px] shrink-0 rounded-full', statusDotClass(status))} />
        <span className="font-mono text-[9.5px] text-muted-foreground">
          {t('planHub.flow.chNo', { n: index + 1, defaultValue: 'ch {{n}}' })}
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
        <div className="mt-2 flex flex-wrap gap-1">
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
    </div>
  );
}

export const FlowChapterCard = memo(FlowChapterCardInner);
