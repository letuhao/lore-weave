import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useStudioHost } from '../host/StudioHostProvider';

// S-11 — the `search` activity-view rail (replaces the old "Built next." stub). A query box +
// a Text/Semantic toggle: submitting opens the `search` dock panel seeded with what was typed
// (via openPanel params — no bus-type change needed). The panel hosts the results and deep-links
// each hit into the editor. This is the entry point; the panel is the results surface.

type SearchMode = 'text' | 'semantic';

export function SearchNavigatorRail() {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<SearchMode>('text');

  const run = () => {
    // Open even on an empty query (the panel's own box takes over) — but seed when present.
    host.openPanel('search', { focus: true, params: { query: input.trim(), mode } });
  };

  return (
    <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2" data-testid="studio-search-rail">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t('search.rail.placeholder', { defaultValue: 'Search your book…' })}
            aria-label={t('search.rail.placeholder', { defaultValue: 'Search your book…' })}
            data-testid="studio-search-rail-input"
            className="w-full rounded-md border bg-background py-1.5 pl-8 pr-2 text-[13px] placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>
      </form>

      <div className="flex rounded-md border p-0.5" role="group" aria-label={t('search.modeLabel', { defaultValue: 'Search mode' })}>
        {(['text', 'semantic'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            aria-pressed={mode === m}
            data-testid={`studio-search-rail-mode-${m}`}
            className={cn(
              'flex-1 rounded px-2 py-1 text-[11px] font-medium transition-colors',
              mode === m ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`search.mode.${m}`, { defaultValue: m === 'text' ? 'Text' : 'Semantic' })}
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={run}
        data-testid="studio-search-rail-go"
        className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground hover:opacity-90"
      >
        {t('search.rail.go', { defaultValue: 'Search' })}
      </button>

      <p className="px-1 text-[11px] leading-relaxed text-muted-foreground">
        {t('search.rail.hint', {
          defaultValue: 'Text finds exact words in your prose; Semantic finds passages by meaning. A hit opens the editor there.',
        })}
      </p>
    </div>
  );
}
