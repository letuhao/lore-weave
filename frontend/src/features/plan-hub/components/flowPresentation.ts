// Plan Hub redesign — lane-flow presentation helpers (pure). ONE home for the status→texture map and
// the arc-subtitle composer so FlowLane / FlowChapterCard never re-derive them (the
// css-var-duplicated-across-two-consumers-drifts lesson). Classes are literal from the sealed mockup
// `design-drafts/plan-hub-redesign/index.html` (status → fill texture; authorship → font/colour).
import type { LaneArc, LaneChapter } from '../layout/laneTree';

/** The four real `outline_node.status` values (NodeStatus). Anything else falls back to 'outline'. */
export type ChapterStatus = 'empty' | 'outline' | 'drafting' | 'done';

export function normStatus(s: string): ChapterStatus {
  return s === 'empty' || s === 'drafting' || s === 'done' ? s : 'outline';
}

/** Chapter card container texture by status (mockup `.ch[data-status=…]`). */
export function chapterCardClass(status: ChapterStatus): string {
  switch (status) {
    case 'empty':
      return 'border-dashed bg-transparent';
    case 'drafting':
      return 'bg-primary/10 border-primary/40';
    case 'done':
      return 'bg-[hsl(var(--success))]/10 border-[hsl(var(--success))]/40';
    case 'outline':
    default:
      return 'bg-secondary border-border';
  }
}

/** The status dot colour (mockup `.ch[data-status] .dot`). */
export function statusDotClass(status: ChapterStatus): string {
  switch (status) {
    case 'empty':
      return 'bg-muted-foreground/50';
    case 'drafting':
      return 'bg-primary';
    case 'done':
      return 'bg-[hsl(var(--success))]';
    case 'outline':
    default:
      return 'bg-muted-foreground';
  }
}

/** Compose the arc's subtitle line (mockup `.arc-sub`): reading span · description · flags. */
export function arcSubtitle(arc: LaneArc): string {
  const parts: string[] = [];
  if (arc.span) {
    parts.push(
      arc.span.from_order === arc.span.to_order
        ? `chapter ${arc.span.from_order}`
        : `chapters ${arc.span.from_order}–${arc.span.to_order}`,
    );
  }
  if (arc.summary) parts.push(arc.summary);
  if (arc.source === 'mined') parts.push('planner proposed');
  if (!arc.isContiguous) parts.push('non-contiguous');
  if (arc.subArcs.length) parts.push(arc.subArcs.length === 1 ? '1 sub-arc' : `${arc.subArcs.length} sub-arcs`);
  return parts.join(' · ');
}

/** The chapter's reading-order label ("ch 3"), or a dash before it has a position. */
export function chapterNo(chapter: LaneChapter, index: number): string {
  return `ch ${chapter.storyOrder != null ? index + 1 : index + 1}`;
}
