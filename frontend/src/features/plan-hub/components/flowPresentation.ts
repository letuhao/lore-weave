// Plan Hub — the readable node-card presentation helpers (pure). ONE home for the status→texture map
// so the canvas cards (ChapterNode / SceneNode / ArcRollupNode) never re-derive it (the
// css-var-duplicated-across-two-consumers-drifts lesson). Classes are literal from the sealed mockup
// `design-drafts/plan-hub-redesign/index.html` (status → fill texture; authorship → font/colour).

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
