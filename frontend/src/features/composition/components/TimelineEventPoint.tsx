// LOOM Composition (T2.3) — one timeline event: a tick + dot on the axis with a
// chapter-title + summary label (alternating above/below to reduce overlap). Dimmed
// when past the spoiler cutoff. Clickable (→ open its chapter) only when it has a
// chapter_id. Render-only; self-positions via the `x` prop.
import { useTranslation } from 'react-i18next';
import type { TimelineEvent } from '../../knowledge/api';

export const POINT_R = 6;
export const POINT_LABEL_W = 120;

function chapterShort(id: string): string {
  return `…${id.slice(-6)}`;
}

export function TimelineEventPoint({
  event, x, axisY, hidden, labelBelow, onOpen,
}: {
  event: TimelineEvent;
  x: number;
  axisY: number;
  hidden: boolean;
  labelBelow: boolean;
  onOpen: ((chapterId: string) => void) | undefined;
}) {
  const { t } = useTranslation('composition');
  const clickable = !!event.chapter_id && !!onOpen;
  const label = event.chapter_title ?? (event.chapter_id ? chapterShort(event.chapter_id) : '');
  const summary = event.summary ?? event.title;
  const labelY = labelBelow ? axisY + 12 : axisY - 12 - 30;
  const activate = () => { if (event.chapter_id && onOpen) onOpen(event.chapter_id); };

  return (
    <g
      data-testid="timeline-event"
      data-event-id={event.id}
      data-hidden={hidden ? 'true' : 'false'}
      data-chapter={event.chapter_id ?? ''}
      className={hidden ? 'opacity-40' : undefined}
      role={clickable ? 'button' : 'listitem'}
      tabIndex={clickable ? 0 : undefined}
      aria-label={clickable
        ? t('chrono.open_chapter', { defaultValue: 'Open chapter: {{title}}', title: label })
        : summary}
      style={clickable ? { cursor: 'pointer' } : undefined}
      onClick={activate}
      onKeyDown={(e) => {
        if (clickable && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); activate(); }
      }}
    >
      <line x1={x} y1={axisY - 6} x2={x} y2={axisY + 6} className="stroke-border" strokeWidth={1} />
      <circle cx={x} cy={axisY} r={POINT_R} className={hidden ? 'fill-muted-foreground' : 'fill-primary'} />
      <foreignObject x={x - POINT_LABEL_W / 2} y={labelY} width={POINT_LABEL_W} height={30} style={{ overflow: 'visible' }}>
        <div className="pointer-events-none text-center text-[10px] leading-tight">
          <div className="truncate font-medium text-foreground">{label}</div>
          <div className="truncate text-muted-foreground">{summary}</div>
        </div>
      </foreignObject>
    </g>
  );
}
