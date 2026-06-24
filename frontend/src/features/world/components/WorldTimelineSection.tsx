import { useTranslation } from 'react-i18next';
import { useWorldTimeline } from '../hooks/useWorldTimeline';

// D-WORLD-TIMELINE-ROLLUP (FE) — the world timeline rollup: a read-only,
// narrative-ordered merge of every member book's timeline + the world-level
// project (the timeline mirror of WorldGraphSection's graph rollup). Read-only
// by design (editing an event happens in its own project's Timeline tab); this
// is the at-a-glance "what happens across the world" view.
interface Props {
  worldId: string | undefined;
}

function chapterShort(id: string | null): string {
  if (!id) return '';
  return id.length > 8 ? `…${id.slice(-8)}` : id;
}

export function WorldTimelineSection({ worldId }: Props) {
  const { t } = useTranslation('world');
  const { events, sourceCount, truncated, isLoading, error } = useWorldTimeline(worldId);

  return (
    <section className="space-y-2" data-testid="world-timeline-section">
      <h2 className="font-medium">{t('timeline.title', { defaultValue: 'World timeline' })}</h2>
      <p className="text-xs text-muted-foreground">
        {t('timeline.subtitle', {
          defaultValue: 'A read-only roll-up of every member book’s canon timeline, in narrative order.',
        })}
      </p>

      {isLoading ? (
        <Hint>{t('timeline.loading', { defaultValue: 'Loading world timeline…' })}</Hint>
      ) : error ? (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="world-timeline-error"
        >
          {t('timeline.loadFailed', { defaultValue: 'Failed to load the world timeline: {{error}}', error: error.message })}
        </div>
      ) : events.length === 0 ? (
        <Hint>
          {t('timeline.empty', {
            defaultValue: 'No timeline events yet — extract a member book to roll its timeline up here.',
          })}
        </Hint>
      ) : (
        <div className="rounded-md border" data-testid="world-timeline-list">
          <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px] text-muted-foreground">
            <span data-testid="world-timeline-counts">
              {t('timeline.counts', { defaultValue: '{{count}} events', count: events.length })}
            </span>
            <span className="rounded bg-secondary px-1.5 py-0.5" data-testid="world-timeline-sources">
              {t('timeline.sources', { defaultValue: 'across {{count}} book(s)', count: sourceCount })}
            </span>
            {truncated && (
              <span className="text-amber-600 dark:text-amber-400" data-testid="world-timeline-truncated">
                {t('timeline.truncated', { defaultValue: 'showing the first {{n}}', n: events.length })}
              </span>
            )}
          </div>
          <ul className="max-h-[50vh] divide-y overflow-y-auto">
            {events.map((e) => {
              const chapterLabel = e.chapter_title ?? chapterShort(e.chapter_id);
              return (
                <li
                  key={e.id}
                  className="grid grid-cols-[56px_1fr] items-start gap-3 px-3 py-2 text-[12px]"
                  data-testid="world-timeline-row"
                >
                  <span className="pt-[2px] text-right font-mono text-[11px] tabular-nums text-muted-foreground">
                    {e.event_order ?? '—'}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium" title={e.title}>{e.title}</span>
                    {chapterLabel && (
                      <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                        {t('timeline.chapterLabel', { defaultValue: 'Chapter' })}: {chapterLabel}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

const Hint = ({ children }: { children: React.ReactNode }) => (
  <div className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground" data-testid="world-timeline-hint">
    {children}
  </div>
);
