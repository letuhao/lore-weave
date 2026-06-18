// LOOM Composition (T2.2) — one Relationship-Map node: an entity, badged by kind.
// The body is the drag handle AND the re-focus target (click via GraphCanvas; Enter
// via onActivate for keyboard). A ⊞/⊟ button accretes/collapses that node's 1-hop
// without re-focusing. Render-only; self-positions (GraphCanvas doesn't transform).
import { useTranslation } from 'react-i18next';
import type { Pos } from './GraphCanvas';
import type { GraphNode } from '../hooks/useRelationshipMap';

export const ENTITY_NODE_W = 140;
export const ENTITY_NODE_H = 46;

const KIND_DOT: Record<string, string> = {
  character: 'bg-sky-500', location: 'bg-emerald-500', faction: 'bg-amber-500', concept: 'bg-violet-500',
};

export function GraphEntityNode({
  node, pos, isFocus, expanded, onPointerDown, onActivate, onExpand,
}: {
  node: GraphNode;
  pos: Pos;
  isFocus: boolean;
  expanded: boolean;
  onPointerDown: (e: React.PointerEvent) => void;
  onActivate: () => void;
  /** Omit to hide the ⊞ expand affordance — e.g. the world rollup is a flat
   *  union of per-book islands with no per-node ego-expansion. */
  onExpand?: () => void;
}) {
  const { t } = useTranslation('composition');
  return (
    <g transform={`translate(${pos.x}, ${pos.y})`} data-testid="relmap-node" data-entity={node.id} data-focus={isFocus ? 'true' : 'false'}>
      <foreignObject width={ENTITY_NODE_W} height={ENTITY_NODE_H} style={{ overflow: 'visible' }}>
        <div
          data-testid="relmap-node-body"
          role="button"
          tabIndex={0}
          aria-pressed={isFocus}
          aria-label={node.name}
          onPointerDown={onPointerDown}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onActivate(); } }}
          className={
            'flex h-full cursor-grab select-none items-center gap-1 rounded-md border bg-card px-1.5 text-[11px] shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-primary active:cursor-grabbing ' +
            (isFocus ? 'border-primary ring-2 ring-primary/50 ' : 'border-border ')
          }
        >
          <span className={'h-2 w-2 shrink-0 rounded-full ' + (KIND_DOT[node.kind] ?? 'bg-slate-400')} aria-hidden />
          <span className="min-w-0 flex-1 truncate font-medium">{node.name}</span>
          {onExpand && (
            <button
              type="button"
              data-testid="relmap-expand"
              aria-label={expanded ? t('relations.collapse', { defaultValue: 'Collapse' }) : t('relations.expand', { defaultValue: 'Expand' })}
              className="shrink-0 rounded px-1 text-muted-foreground hover:text-primary"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onExpand(); }}
            >
              {expanded ? '⊟' : '⊞'}
            </button>
          )}
        </div>
      </foreignObject>
    </g>
  );
}
