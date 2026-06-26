// LOOM Composition (M6) — "Canon at chapter N" inspector.
//
// A writer panel answering "what does canon know as of chapter N" from existing
// windowed data. Mounted two ways: at a what-if BRANCH POINT (canon right before the
// divergence) and as a per-scene studio panel. Glossary PRESENCE and knowledge
// CANON-STATE are labeled by source distinctly (two stores, may disagree).
import { useTranslation } from 'react-i18next';
import { useCanonAtChapter, type CanonAtChapterInput } from '../hooks/useCanonAtChapter';

const RELEVANCE_STYLE: Record<string, string> = {
  major: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  appears: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200',
  mentioned: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300',
};

export function CanonAtChapterPanel(props: CanonAtChapterInput & { chapterLabel?: string }) {
  const { t } = useTranslation('composition');
  const canon = useCanonAtChapter(props);

  if (!props.chapterId) {
    return (
      <div data-testid="canonview-empty" className="p-3 text-xs text-muted-foreground">
        {t('canonview.noChapter', { defaultValue: 'No chapter in focus — open a scene to inspect canon as of its chapter.' })}
      </div>
    );
  }

  return (
    <div data-testid="canonview-panel" className="flex h-full flex-col gap-3 overflow-y-auto p-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="font-medium">{t('canonview.title', { defaultValue: 'Canon as of' })}</span>
        <span className="rounded bg-indigo-100 px-1.5 py-0.5 font-mono text-[10px] text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-200">
          {props.chapterLabel ?? t('canonview.chapterN', { defaultValue: 'chapter {{n}}', n: (props.chapterIndex ?? 0) + 1 })}
        </span>
      </div>

      {canon.isLoading && <div data-testid="canonview-loading" className="text-muted-foreground">{t('canonview.loading', { defaultValue: 'Reading canon…' })}</div>}

      {!canon.isLoading && canon.isEmpty && (
        <div data-testid="canonview-not-analyzed" className="rounded border border-dashed bg-muted/30 p-2 text-muted-foreground">
          {t('canonview.notAnalyzed', { defaultValue: 'This chapter is not yet analyzed — extract the book to populate canon.' })}
        </div>
      )}

      {!canon.isLoading && !canon.isEmpty && (
        <>
          {/* Source: GLOSSARY — entities present in / established by this chapter. */}
          <section data-testid="canonview-presence">
            <h4 className="mb-1 font-semibold text-muted-foreground">
              {t('canonview.presence', { defaultValue: 'Present in this chapter' })}
              <span className="ml-1 font-normal opacity-60">{t('canonview.srcGlossary', { defaultValue: '· glossary' })}</span>
            </h4>
            {canon.present.length === 0 ? (
              <p className="text-muted-foreground/70">{t('canonview.noneHere', { defaultValue: 'No entities linked to this chapter.' })}</p>
            ) : (
              <ul className="flex flex-wrap gap-1">
                {canon.present.map((e) => (
                  <li key={e.entity_id} className={`rounded px-1.5 py-0.5 ${RELEVANCE_STYLE[e.relevance] ?? RELEVANCE_STYLE.mentioned}`}>
                    {e.name}
                    {e.mention_count > 0 && <span className="ml-1 font-mono opacity-70">×{e.mention_count}</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {canon.established != null && (
            <section data-testid="canonview-established">
              <h4 className="mb-1 font-semibold text-muted-foreground">
                {t('canonview.established', { defaultValue: 'Established by now' })}
                <span className="ml-1 font-normal opacity-60">{t('canonview.countGlossary', { defaultValue: '· {{n}} entities', n: canon.established.length })}</span>
              </h4>
              <ul className="flex flex-wrap gap-1">
                {canon.established.slice(0, 60).map((e) => (
                  <li key={e.entity_id} className="rounded bg-neutral-100 px-1.5 py-0.5 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300" title={t('canonview.coverage', { defaultValue: 'appears in {{pct}}% of chapters', pct: Math.round(e.coverage_pct * 100) })}>
                    {e.name}
                  </li>
                ))}
                {canon.established.length > 60 && <li className="px-1 text-muted-foreground/60">+{canon.established.length - 60}</li>}
              </ul>
            </section>
          )}

          {/* Source: KNOWLEDGE — canon state (statuses + timeline) as of this chapter. */}
          <section data-testid="canonview-canonstate">
            <h4 className="mb-1 font-semibold text-muted-foreground">
              {t('canonview.canonState', { defaultValue: 'Canon state' })}
              <span className="ml-1 font-normal opacity-60">{t('canonview.srcKnowledge', { defaultValue: '· knowledge' })}</span>
            </h4>
            {canon.canonState && !canon.canonState.windowAvailable ? (
              <p className="text-amber-700 dark:text-amber-300">{t('canonview.windowUnavailable', { defaultValue: 'Reading position unknown — window unavailable for this chapter.' })}</p>
            ) : (
              <div className="flex flex-wrap gap-3 text-muted-foreground">
                {canon.canonState && (
                  <>
                    <span>{t('canonview.active', { defaultValue: '{{n}} active', n: canon.canonState.active })}</span>
                    <span>{t('canonview.gone', { defaultValue: '{{n}} gone', n: canon.canonState.gone })}</span>
                  </>
                )}
                {canon.timeline && <span>{t('canonview.events', { defaultValue: '{{n}} timeline events', n: canon.timeline.events })}</span>}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
