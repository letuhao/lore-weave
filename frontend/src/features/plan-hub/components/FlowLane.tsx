// Plan Hub redesign — one ARC LANE (mockup `.lane`), recursive for sub-arcs (`.lane.sub`). A root lane
// is bounded + horizontally resizable (its chapters WRAP downward, never off the right edge); a
// sub-arc is an inset lane with a left spine + a "sub-arc" tag so the nesting is explicit. Authorship
// colours the border (amber authored / teal mined). Keyset windowing is unchanged: a collapsed lane
// shows only its header; "+ N more" pages the next chapter window in.
import { memo } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { ArcPagination } from '../types';
import type { LaneArc } from '../layout/laneTree';
import { FlowChapterCard } from './FlowChapterCard';
import { arcSubtitle, chapterDisplayNo } from './flowPresentation';

export interface FlowLaneProps {
  arc: LaneArc;
  arcPagination: Record<string, ArcPagination>;
  selectedId: string | null;
  /** book-service chapter_id currently open in the editor (for the "you are here" outline). */
  activeChapterId: string | null;
  /** PH15 find — matched card ids (ringed). undefined ⇒ no active query. */
  matchedIds?: Set<string>;
  onSelect: (id: string) => void;
  onToggleArc: (arcId: string) => void;
  onToggleChapter: (chapterNodeId: string) => void;
  onLoadMoreArc: (arcId: string) => void;
  onAddChapter: ((arcId: string) => void) | null;
  onAddScene: ((chapterNodeId: string, bookChapterId: string) => void) | null;
  onAddSubArc: ((parentArcId: string) => void) | null;
  addingChild: boolean;
  /** The arc pick-list for the per-chapter "move to arc" control. */
  arcOptions: { id: string; title: string; depth: number }[];
  /** Re-file a chapter under another arc. Null ⇒ no EDIT grant. */
  onMoveChapterToArc: ((chapterNodeId: string, arcId: string) => void) | null;
}

function Chip({ children, tone = 'plain', testid }: { children: React.ReactNode; tone?: 'plain' | 'machine' | 'warn'; testid?: string }) {
  return (
    <span
      data-testid={testid}
      className={cn(
        'whitespace-nowrap rounded border px-1.5 py-0.5 font-mono text-[9px] tracking-wide',
        tone === 'machine' && 'border-accent/45 bg-accent/[0.09] text-accent',
        tone === 'warn' && 'border-amber-500/45 bg-amber-500/10 text-amber-600 dark:text-amber-400',
        tone === 'plain' && 'border-border text-muted-foreground',
      )}
    >
      {children}
    </span>
  );
}

function FlowLaneInner(props: FlowLaneProps) {
  const { arc, arcPagination, selectedId, activeChapterId, matchedIds, onSelect, onToggleArc, onToggleChapter,
    onLoadMoreArc, onAddChapter, onAddScene, onAddSubArc, addingChild, arcOptions, onMoveChapterToArc } = props;
  const { t } = useTranslation('studio');
  const machine = arc.source === 'mined';
  const isSub = arc.depth > 0;
  const pg = arcPagination[arc.id];
  const sub = arcSubtitle(arc);

  return (
    <div
      data-testid={`flow-lane-${arc.id}`}
      data-source={arc.source}
      className={cn(
        'mb-3.5 overflow-hidden rounded-lg border',
        machine ? 'border-accent/40 bg-accent/[0.05]' : 'border-primary/35 bg-primary/[0.04]',
        isSub && 'mx-3 mb-3 mt-0.5 border-l-[3px] border-l-primary/45',
        selectedId === arc.id && 'outline outline-2 outline-primary outline-offset-1',
        matchedIds?.has(arc.id) && 'ring-2 ring-yellow-500',
      )}
      style={isSub ? undefined : { width: '62%', minWidth: 360, maxWidth: '100%', resize: 'horizontal' }}
    >
      <div className="flex items-start gap-2 border-b border-border/70 bg-background/40 px-3 py-2.5">
        <button
          type="button"
          data-testid={`flow-lane-toggle-${arc.id}`}
          onClick={() => onToggleArc(arc.id)}
          className="mt-0.5 select-none text-xs text-muted-foreground hover:text-foreground"
          aria-label={arc.collapsed ? 'Expand lane' : 'Collapse lane'}
        >
          {arc.collapsed ? '▸' : '▾'}
        </button>
        {isSub && (
          <span
            data-testid={`flow-subtag-${arc.id}`}
            className="mt-0.5 shrink-0 rounded border border-primary/50 px-1.5 py-px font-mono text-[8.5px] uppercase tracking-widest text-primary"
          >
            {t('planHub.flow.subArcTag', 'sub-arc')}
          </span>
        )}
        <div className="min-w-0 flex-1 cursor-pointer" onClick={() => onSelect(arc.id)}>
          <div className={cn('font-semibold leading-tight text-foreground/95', machine ? 'font-mono text-[13px]' : 'font-serif text-[15px]')}>
            {arc.title || t('planHub.flow.untitledArc', 'Untitled arc')}
          </div>
          {sub && <div className="mt-0.5 text-[11px] text-muted-foreground">{sub}</div>}
        </div>
        <div className="mt-0.5 flex shrink-0 items-center gap-1.5">
          {pg && pg.hasMore && pg.total > 0 && (
            <Chip testid={`flow-lane-count-${arc.id}`}>{pg.loaded}/{pg.total}</Chip>
          )}
          {arc.chapterCount > 0 && <Chip>{t('planHub.flow.chCount', { n: arc.chapterCount, defaultValue: '{{n}} ch' })}</Chip>}
          {!arc.isContiguous && <Chip tone="warn" testid={`flow-lane-warn-${arc.id}`}>{t('planHub.flow.gap', '⚠ gap')}</Chip>}
          {machine && arc.collapsed && <Chip tone="machine" testid={`flow-lane-ai-${arc.id}`}>{t('planHub.flow.aiCollapsed', 'AI · collapsed')}</Chip>}
        </div>
      </div>

      {!arc.collapsed && (
        <>
          <div className="flex flex-wrap items-start gap-2.5 px-3 py-3">
            {arc.chapters.map((ch, i) => (
              <FlowChapterCard
                key={ch.id}
                chapter={ch}
                displayNo={chapterDisplayNo(arc, i)}
                selected={selectedId === ch.id}
                isHere={!!activeChapterId && ch.chapterId === activeChapterId}
                matched={!!matchedIds?.has(ch.id)}
                onSelect={onSelect}
                onToggleScenes={onToggleChapter}
                onAddScene={onAddScene}
                addingChild={addingChild}
                currentArcId={arc.id}
                arcOptions={arcOptions}
                onMoveToArc={onMoveChapterToArc}
              />
            ))}
            {pg?.hasMore && (
              <button
                type="button"
                data-testid={`flow-lane-more-${arc.id}`}
                disabled={pg.loading}
                onClick={() => onLoadMoreArc(arc.id)}
                className="cursor-pointer self-center rounded border border-accent/50 px-3 py-2 font-mono text-[10px] text-accent hover:border-accent disabled:opacity-50"
              >
                {pg.loading ? '…' : t('planHub.flow.moreChapters', { n: Math.max(pg.total - pg.loaded, 0), defaultValue: '+ {{n}} more' })}
              </button>
            )}
            {onAddChapter && (
              <button
                type="button"
                data-testid={`flow-add-chapter-${arc.id}`}
                disabled={addingChild}
                onClick={() => onAddChapter(arc.id)}
                className="cursor-pointer self-center rounded border border-dashed border-border px-3 py-2 font-mono text-[10px] text-muted-foreground/80 hover:border-primary/55 hover:text-primary disabled:opacity-50"
              >
                {t('planHub.flow.addChapter', '+ chapter')}
              </button>
            )}
            {onAddSubArc && (arc.kind === 'arc' || arc.kind === 'saga') && (
              <button
                type="button"
                data-testid={`flow-add-subarc-${arc.id}`}
                disabled={addingChild}
                onClick={() => onAddSubArc(arc.id)}
                className="cursor-pointer self-center rounded border border-dashed border-border px-3 py-2 font-mono text-[10px] text-muted-foreground/80 hover:border-primary/55 hover:text-primary disabled:opacity-50"
              >
                {t('planHub.flow.addSubArc', '+ sub-arc')}
              </button>
            )}
          </div>
          {arc.subArcs.map((s) => (
            <FlowLane key={s.id} {...props} arc={s} />
          ))}
        </>
      )}
    </div>
  );
}

export const FlowLane = memo(FlowLaneInner);
