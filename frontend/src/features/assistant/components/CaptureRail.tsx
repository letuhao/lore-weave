// WS-1.10 view — the "today so far" rail: the People / Projects the capture pipeline noticed as the
// user talked. Pure render (CLAUDE.md MVC) — data comes from useCaptureRail via the home strip.
import type { GlossaryEntitySummary } from '@/features/glossary/types';

const KIND_ICON: Record<string, string> = {
  colleague: '👤',
  project: '▤',
  meeting: '📅',
  decision: '✓',
  task: '☐',
  jargon: '📖',
  org: '🏢',
};

export function CaptureRail({
  entities,
  loading,
  captureOn,
}: {
  entities: GlossaryEntitySummary[];
  loading: boolean;
  captureOn: boolean;
}) {
  return (
    <div data-testid="assistant-capture-rail" className="rounded-lg border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <h3 className="text-sm font-semibold">Today so far</h3>
        {captureOn && (
          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-600">
            live
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Things I&apos;m noticing as we talk. Nothing is saved to your diary until you review it tonight.
      </p>

      {entities.length === 0 ? (
        <p data-testid="capture-rail-empty" className="text-sm text-muted-foreground">
          {loading
            ? 'Listening…'
            : captureOn
              ? 'Nothing captured yet — tell me about your day.'
              : 'Turn on capture to start noticing people and projects.'}
        </p>
      ) : (
        <ul className="space-y-2">
          {entities.map((e) => (
            <li key={e.entity_id} data-testid="capture-entity" className="flex items-start gap-2">
              <span aria-hidden className="mt-0.5 text-base leading-none">
                {KIND_ICON[e.kind.code] ?? '•'}
              </span>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium" data-testid="capture-entity-name">
                  {e.display_name}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {e.kind.name}
                  {e.short_description ? ` · ${e.short_description}` : ''}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
