import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useRawSearch, type RawSearchMode } from '../hooks/useRawSearch';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { RawSearchResultCard } from './RawSearchResultCard';

// "View" surface for raw search (MVC: logic in useRawSearch, render here).

export interface RawSearchPanelProps {
  bookId: string;
}

const MODES: RawSearchMode[] = ['hybrid', 'lexical'];

export function RawSearchPanel({ bookId }: RawSearchPanelProps) {
  const { t } = useTranslation('rawSearch');
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<RawSearchMode>('hybrid');
  // Debounce so a real BE query doesn't fire on every keystroke (review-impl MED-2).
  const debouncedQuery = useDebouncedValue(input, 250);
  const { hits, disabled, isFetching, error, degraded } = useRawSearch(
    bookId, debouncedQuery, { mode },
  );

  // Jump-to-source: v1 navigates to the book's chapters hub. Precise
  // chapter-open + scroll-to-block is deferred (D-RAWSEARCH-FE-JUMP-PRECISION).
  const onJump = () => navigate(`/books/${bookId}`);
  const isDegraded = Object.keys(degraded).length > 0;

  return (
    <div className="flex flex-col gap-3" data-testid="raw-search-panel">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t('placeholder')}
            aria-label={t('placeholder')}
            data-testid="raw-search-input"
            className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>
        <div
          className="flex rounded-md border p-0.5"
          role="group"
          aria-label={t('mode_label')}
        >
          {MODES.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              data-testid={`raw-search-mode-${m}`}
              className={cn(
                'rounded px-2 py-1 text-xs font-medium transition-colors',
                mode === m
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(`mode_${m}`)}
            </button>
          ))}
        </div>
      </div>

      {isDegraded && !error && (
        <p
          className="text-xs text-amber-600 dark:text-amber-400"
          data-testid="raw-search-degraded"
        >
          {t('degraded')}
        </p>
      )}
      {error && (
        <p className="text-sm text-destructive" role="alert" data-testid="raw-search-error">
          {t('error')}
        </p>
      )}
      {!error && disabled && (
        <p className="text-sm text-muted-foreground" data-testid="raw-search-hint">
          {t('hint')}
        </p>
      )}
      {!error && !disabled && isFetching && hits.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="raw-search-loading">
          {t('loading')}
        </p>
      )}
      {!error && !disabled && !isFetching && hits.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="raw-search-empty">
          {t('no_results')}
        </p>
      )}
      {hits.length > 0 && (
        <ul className="divide-y rounded-md border" data-testid="raw-search-results">
          {hits.map((hit) => (
            <RawSearchResultCard
              key={`${hit.chapterId}:${hit.matchType}:${hit.location.blockIndex ?? hit.location.chunkIndex}`}
              hit={hit}
              onJump={onJump}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
