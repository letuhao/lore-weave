// LOOM Composition (WS-B3 M1/M2) — one ephemeral what-if ALTERNATE as a graph node.
//
// A dashed/tinted counterpart to SceneNode, drawn beside canon so the branch reads as
// a parallel "what-if" (purple, like DerivativeBanner). Not a persisted scene. M2 adds
// the per-node lifecycle: ✦ Generate → (generating) → judge badge (critic dims) + View
// (opens the ghost in the preview strip). Render-only; logic in useSceneWhatIf /
// useWhatIfTakes.
import { useTranslation } from 'react-i18next';
import type { WhatIfAlt } from '../hooks/useSceneWhatIf';
import { NODE_H, NODE_W, type Pos } from './sceneGraphLayout';

// Compact judge chip colour by score (same thresholds as the WS-B1 critic surface).
function dimClass(v: number | null): string {
  if (v == null) return 'text-purple-400';
  if (v >= 7) return 'text-emerald-600 dark:text-emerald-400';
  if (v >= 5) return 'text-amber-600 dark:text-amber-400';
  return 'text-rose-600 dark:text-rose-400';
}

export function WhatIfAltNode({
  alt, pos, onRemove, onGenerate, onView,
}: {
  alt: WhatIfAlt;
  pos: Pos;
  onRemove: () => void;
  onGenerate: () => void;
  onView: () => void;
}) {
  const { t } = useTranslation('composition');
  const judge = alt.take?.judge;
  return (
    <g transform={`translate(${pos.x}, ${pos.y})`} data-testid="whatif-alt-node" data-alt={alt.id} data-status={alt.status}>
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

          {alt.status === 'idle' && (
            <button
              type="button" data-testid={`whatif-alt-generate-${alt.id}`}
              className="self-start rounded border border-purple-300 px-1.5 py-0.5 text-purple-700 hover:bg-purple-100 dark:border-purple-700 dark:text-purple-300 dark:hover:bg-purple-900/40"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onGenerate(); }}
            >
              ✦ {t('whatif.generate', { defaultValue: 'Generate take' })}
            </button>
          )}
          {alt.status === 'generating' && (
            <span data-testid={`whatif-alt-generating-${alt.id}`} className="text-[10px] text-purple-700/70 dark:text-purple-300/70">
              {t('whatif.generating', { defaultValue: 'Generating…' })}
            </span>
          )}
          {alt.status === 'error' && (
            <button
              type="button" data-testid={`whatif-alt-retry-${alt.id}`}
              className="self-start rounded border border-rose-300 px-1.5 py-0.5 text-rose-700 hover:bg-rose-50 dark:border-rose-700 dark:text-rose-300"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onGenerate(); }}
            >
              {t('whatif.retry', { defaultValue: 'Failed — retry' })}
            </button>
          )}
          {alt.status === 'ready' && (
            <div className="flex items-center justify-between gap-1">
              {/* judge badge — critic dims (null until the async critique returns) */}
              <span data-testid={`whatif-alt-judge-${alt.id}`} className="flex gap-1 font-mono text-[10px]">
                {judge ? (
                  <>
                    <span className={dimClass(judge.coherence)} title={t('whatif.coherence', { defaultValue: 'Coherence' })}>C{judge.coherence ?? '–'}</span>
                    <span className={dimClass(judge.voice_match)} title={t('whatif.voice', { defaultValue: 'Voice' })}>V{judge.voice_match ?? '–'}</span>
                    <span className={dimClass(judge.pacing)} title={t('whatif.pacing', { defaultValue: 'Pacing' })}>P{judge.pacing ?? '–'}</span>
                  </>
                ) : (
                  <span className="text-purple-400">{t('whatif.judging', { defaultValue: 'judging…' })}</span>
                )}
              </span>
              <button
                type="button" data-testid={`whatif-alt-view-${alt.id}`}
                className="shrink-0 rounded px-1 text-indigo-600 hover:underline dark:text-indigo-400"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => { e.stopPropagation(); onView(); }}
              >
                {t('whatif.view', { defaultValue: 'View' })}
              </button>
            </div>
          )}
        </div>
      </foreignObject>
    </g>
  );
}
