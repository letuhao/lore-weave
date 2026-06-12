// LOOM Composition (T1.3) — one scene as a graph node. An SVG <g> at (x,y) with a
// <foreignObject> body so the title truncates + the open (↗) button render as real
// HTML. The whole body is a drag handle (pointer-down bubbles to the canvas, which
// decides drag-vs-click by movement threshold); the open button stops propagation
// so a jump never starts a drag/select. Selection (for link-create) shows a ring.
// Render-only: drag/select/open intent bubble up.
import { useTranslation } from 'react-i18next';
import type { OutlineNode } from '../types';
import { NODE_H, NODE_W, type Pos } from './sceneGraphLayout';

const DOT: Record<OutlineNode['status'], string> = {
  done: 'bg-emerald-500', drafting: 'bg-amber-500', outline: 'bg-slate-400', empty: 'bg-slate-300',
};

export function SceneNode({
  node, pos, selected, onPointerDown, onSelect, onOpen,
}: {
  node: OutlineNode;
  pos: Pos;
  selected: boolean;
  onPointerDown: (e: React.PointerEvent) => void;
  onSelect: () => void;
  onOpen: () => void;
}) {
  const { t } = useTranslation('composition');
  return (
    <g transform={`translate(${pos.x}, ${pos.y})`} data-testid="scene-node" data-node={node.id} data-selected={selected ? 'true' : 'false'}>
      <foreignObject width={NODE_W} height={NODE_H} style={{ overflow: 'visible' }}>
        {/* Selectable card (role=button + Enter/Space) so the pick-two-to-link flow
            works by keyboard, not just pointer drag/click. Drag is a pointer-only
            enhancement; auto-layout positions the node for keyboard users. */}
        <div
          data-testid="scene-node-body"
          role="button"
          tabIndex={0}
          aria-pressed={selected}
          aria-label={node.title || t('untitledScene', { defaultValue: 'Untitled scene' })}
          onPointerDown={onPointerDown}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(); } }}
          className={
            'flex h-full cursor-grab select-none flex-col gap-0.5 rounded-md border bg-card p-1.5 text-[11px] shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-primary active:cursor-grabbing ' +
            (selected ? 'border-primary ring-2 ring-primary/50 ' : 'border-border ')
          }
        >
          <div className="flex items-center gap-1">
            <span className={'h-2 w-2 shrink-0 rounded-full ' + DOT[node.status]} aria-hidden />
            <span className="min-w-0 flex-1 truncate font-medium">{node.title || t('untitledScene', { defaultValue: 'Untitled scene' })}</span>
            <button
              type="button"
              data-testid="scene-node-open"
              aria-label={t('scenegraph.open', { defaultValue: 'Open scene' })}
              className="shrink-0 rounded px-1 text-muted-foreground hover:text-primary"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onOpen(); }}
            >
              ↗
            </button>
          </div>
          {node.synopsis && <span className="line-clamp-2 text-[10px] text-muted-foreground">{node.synopsis}</span>}
        </div>
      </foreignObject>
    </g>
  );
}
