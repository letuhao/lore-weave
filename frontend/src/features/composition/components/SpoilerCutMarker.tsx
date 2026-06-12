// LOOM Composition (T2.3) — the "AI sees ≤ here" spoiler cutoff: a dashed vertical
// line on the timeline axis with a caption. Positioned by the parent (TimelineView)
// at the boundary between the last visible and first hidden event. Render-only.
import { useTranslation } from 'react-i18next';

export function SpoilerCutMarker({ x, top, bottom }: { x: number; top: number; bottom: number }) {
  const { t } = useTranslation('composition');
  return (
    <g data-testid="timeline-cut" data-x={Math.round(x)}>
      <line
        x1={x} y1={top} x2={x} y2={bottom}
        className="stroke-amber-500"
        strokeWidth={1.5}
        strokeDasharray="4 3"
      />
      <foreignObject x={x - 60} y={top - 16} width={120} height={16} style={{ overflow: 'visible' }}>
        <div className="pointer-events-none whitespace-nowrap text-center text-[9px] font-medium text-amber-600 dark:text-amber-400">
          {t('chrono.spoiler_cut', { defaultValue: 'AI sees ≤ here' })}
        </div>
      </foreignObject>
    </g>
  );
}
