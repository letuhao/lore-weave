// LOOM Composition (T1.3) — one scene edge. Drawn center-to-center between two
// node boxes with an arrowhead; `setup_payoff` is solid, `custom` is dashed. A
// transparent fat "hit" line makes the thin edge clickable; clicking selects it,
// which reveals a ✕ delete button + the label at the midpoint. Render-only.
import { useTranslation } from 'react-i18next';
import type { SceneLink } from '../types';
import { NODE_H, NODE_W, type Pos } from './sceneGraphLayout';

const center = (p: Pos) => ({ x: p.x + NODE_W / 2, y: p.y + NODE_H / 2 });

export function SceneEdge({
  link, from, to, selected, onSelect, onDelete,
}: {
  link: SceneLink;
  from: Pos;
  to: Pos;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation('composition');
  const a = center(from);
  const b = center(to);
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const color = selected ? 'var(--primary, #6366f1)' : '#94a3b8';
  return (
    <g data-testid="scene-edge" data-kind={link.kind} data-selected={selected ? 'true' : 'false'}>
      {/* fat invisible hit target so the thin edge is easy to click */}
      <line
        x1={a.x} y1={a.y} x2={b.x} y2={b.y}
        stroke="transparent" strokeWidth={14} style={{ cursor: 'pointer' }}
        onPointerDown={(e) => { e.stopPropagation(); onSelect(); }}
      />
      <line
        x1={a.x} y1={a.y} x2={b.x} y2={b.y}
        stroke={color} strokeWidth={selected ? 2.5 : 1.5}
        strokeDasharray={link.kind === 'custom' ? '5 4' : undefined}
        markerEnd="url(#scene-arrow)" pointerEvents="none"
      />
      {(link.label || selected) && (
        <foreignObject x={mid.x - 60} y={mid.y - 14} width={120} height={28} style={{ overflow: 'visible' }}>
          <div className="flex items-center justify-center gap-1">
            {link.label && (
              <span className="truncate rounded bg-background/90 px-1 text-[10px] text-muted-foreground shadow-sm">{link.label}</span>
            )}
            {selected && (
              <button
                type="button"
                data-testid="scene-edge-delete"
                aria-label={t('scenegraph.deleteLink', { defaultValue: 'Delete link' })}
                className="rounded bg-background px-1 text-[10px] text-muted-foreground shadow-sm hover:text-destructive"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => { e.stopPropagation(); onDelete(); }}
              >
                ✕
              </button>
            )}
          </div>
        </foreignObject>
      )}
    </g>
  );
}
