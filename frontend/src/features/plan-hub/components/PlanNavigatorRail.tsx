// Plan Hub v2 (24 §Phase H6 / PH25) — the Plan NAVIGATOR RAIL. A render-only sidebar tree over the
// arc shell (structure_node: saga → arc → sub-arc), the LIST rendering of the same data the Hub
// canvas draws (PH25). It is NOT a dock panel — no catalog row, no `ui_open_studio_panel` enum entry.
//
// The VS-Code Explorer-vs-Source-Control analogy: a row click focuses the HUB GRAPH (onFocusNode),
// NOT the Editor — that's the delta vs the Manuscript Navigator, whose row click opens the Editor.
// This component only EXPOSES the callback (the hub-focus click contract); the orchestrator wires it
// to pan/select the canvas. Mirrors OutlineNodeRow / ManuscriptNavigator row + indent styling
// (DOCK-2): a caret button for expand/collapse (a SIBLING of the focus button — no nested-button
// a11y issue), depth indentation, a selected-row accent bar, and a right-aligned chapter-count badge.
// It cannot reuse OutlineNodeRow itself: that row is bound to the legacy `outline_node` type and its
// CRUD/dnd machinery; the rail is read-only over `structure_node` (ArcListNode) — a different model.
import { useTranslation } from 'react-i18next';
import { ChevronRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePlanNavigator } from '../hooks/usePlanNavigator';

interface Props {
  bookId: string;
  /** Row click → focus this structure node on the Hub graph (the hub-focus click contract, PH25).
   *  The rail exposes the intent; the orchestrator pans/selects the canvas. */
  onFocusNode: (nodeId: string) => void;
  /** The currently focused node id (highlight) — mirrors the canvas selection. */
  selectedId: string | null;
  /** Empty-state ORIGIN door (F8): open the plan-hub so its origin verb ("Start your first arc")
   *  can create the book's first arc. Without this the empty rail is a dead end — the reason F8
   *  exists. Mirrors the Manuscript rail's `+` (StudioSideBar wires both to the same open-plan door). */
  onOpenPlan?: () => void;
}

export function PlanNavigatorRail({ bookId, onFocusNode, selectedId, onOpenPlan }: Props) {
  const { t } = useTranslation('studio');
  const { rows, loading, error, toggle } = usePlanNavigator(bookId);

  return (
    <div data-testid="plan-nav" className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-[34px] flex-shrink-0 items-center border-b pl-3 pr-2 text-[10px] font-bold uppercase tracking-[0.06em] text-muted-foreground">
        {t('planNav.title', { defaultValue: 'Plan' })}
      </div>

      {error && (
        <div className="px-3 py-1.5 text-[11px] text-amber-600" data-testid="plan-nav-error">
          {error}
        </div>
      )}

      <div data-testid="plan-nav-scroll" className="min-h-0 flex-1 overflow-y-auto py-1">
        {loading ? (
          <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            {t('planNav.loading', { defaultValue: 'Loading…' })}
          </div>
        ) : rows.length === 0 && !error ? (
          // F8 — a guided empty state with a real door, not a dead end. The copy explains WHY the
          // panel is empty (mirrors the sibling ArcInspectorPanel's wording); the button hands off to
          // the plan-hub origin flow, the same door the Manuscript rail's `+` uses. Gated on
          // `onOpenPlan` so a host-less render (or a caller that opts out) degrades to copy-only.
          <div data-testid="plan-nav-empty" className="flex flex-col items-center gap-2.5 p-4 text-center">
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              {t('planNav.emptyGuided', {
                defaultValue: 'No arcs yet — the plan is the spec that steers your book. Lay out its arcs and chapters to get started.',
              })}
            </p>
            {onOpenPlan && (
              <button
                type="button"
                data-testid="plan-nav-plan-cta"
                onClick={onOpenPlan}
                className="rounded border border-border bg-background px-3 py-1 text-[11px] font-semibold hover:border-ring"
              >
                {t('planNav.planCta', { defaultValue: 'Plan this book' })}
              </button>
            )}
          </div>
        ) : (
          rows.map(({ node, depth, hasChildren, expanded }) => {
            const selected = selectedId === node.id;
            const isRoot = depth === 0;
            return (
              <div
                key={node.id}
                data-testid={`plan-nav-row-${node.id}`}
                data-depth={depth}
                className={cn('group relative flex items-center', selected && 'bg-primary/10')}
                style={{ paddingLeft: 8 + depth * 16 }}
              >
                {/* selected-row accent bar (mockup .row.active::before) */}
                {selected && <span className="pointer-events-none absolute left-0 top-0 h-full w-[2px] bg-primary" />}

                {/* caret (expandable) or a leaf spacer — a sibling button, never nested in the focus one */}
                {hasChildren ? (
                  <button
                    type="button"
                    data-testid={`plan-nav-caret-${node.id}`}
                    aria-label={expanded ? 'collapse' : 'expand'}
                    aria-expanded={expanded}
                    onClick={() => toggle(node.id)}
                    className="flex h-4 w-4 flex-shrink-0 items-center justify-center text-muted-foreground hover:text-foreground"
                  >
                    <ChevronRight className={cn('h-3 w-3 transition-transform', expanded && 'rotate-90')} />
                  </button>
                ) : (
                  <span className="h-4 w-4 flex-shrink-0" />
                )}

                {/* row body → focus the node on the Hub graph (NOT open the Editor) */}
                <button
                  type="button"
                  data-testid={`plan-nav-focus-${node.id}`}
                  data-kind={node.kind}
                  onClick={() => onFocusNode(node.id)}
                  className={cn(
                    'flex min-w-0 flex-1 items-center gap-1.5 py-1 pr-2 text-left text-xs transition-colors',
                    selected ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
                    isRoot ? 'font-bold' : 'font-medium',
                  )}
                >
                  <span className="min-w-0 flex-1 truncate" title={node.title}>{node.title || node.kind}</span>
                  {node.chapter_count > 0 && (
                    <span
                      data-testid={`plan-nav-count-${node.id}`}
                      className={cn('ml-auto flex-shrink-0 font-mono text-[9px]', isRoot ? 'text-accent' : 'text-muted-foreground/70')}
                    >
                      {node.chapter_count}
                    </span>
                  )}
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
