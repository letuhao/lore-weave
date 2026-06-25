// LOOM Composition (WS-B3 M1) — one ephemeral what-if ALTERNATE as a graph node.
//
// A dashed/tinted counterpart to SceneNode, drawn beside canon so the branch reads as
// a parallel "what-if" (UX language mirrors the purple DerivativeBanner). It is NOT a
// persisted scene — no status dot / open-scene jump; just the alt title + a ✕ to drop
// it. M2 adds the per-node Generate-take + judge badge here. Render-only.
import { useTranslation } from 'react-i18next';
import { NODE_H, NODE_W, type Pos } from './sceneGraphLayout';

export function WhatIfAltNode({
  alt, pos, onRemove,
}: {
  alt: { id: string; title: string };
  pos: Pos;
  onRemove: () => void;
}) {
  const { t } = useTranslation('composition');
  return (
    <g transform={`translate(${pos.x}, ${pos.y})`} data-testid="whatif-alt-node" data-alt={alt.id}>
      <foreignObject width={NODE_W} height={NODE_H} style={{ overflow: 'visible' }}>
        <div
          data-testid="whatif-alt-body"
          className="flex h-full select-none flex-col gap-0.5 rounded-md border border-dashed border-purple-400 bg-purple-50/70 p-1.5 text-[11px] text-purple-900 shadow-sm dark:border-purple-600 dark:bg-purple-950/40 dark:text-purple-200"
        >
          <div className="flex items-center gap-1">
            <span aria-hidden className="shrink-0">⑂</span>
            <span className="min-w-0 flex-1 truncate font-medium">{alt.title}</span>
            <button
              type="button"
              data-testid={`whatif-alt-remove-${alt.id}`}
              aria-label={t('whatif.removeAlt', { defaultValue: 'Remove alternate' })}
              className="shrink-0 rounded px-1 text-purple-500 hover:text-purple-800 dark:hover:text-purple-100"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onRemove(); }}
            >
              ✕
            </button>
          </div>
          <span className="text-[10px] text-purple-700/70 dark:text-purple-300/70">
            {t('whatif.altHint', { defaultValue: 'Draft an alternate (preview) — not saved until you promote.' })}
          </span>
        </div>
      </foreignObject>
    </g>
  );
}
