import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, FileText, MessageSquare, BookMarked } from 'lucide-react';
import { useDrawerSearch } from '@/features/knowledge/hooks/useDrawerSearch';
import { useDebouncedValue } from '@/features/raw-search/hooks/useDebouncedValue';

// S-11 — the studio search panel's SEMANTIC mode: a thin list over the existing
// `memory_search` / drawers hook. Net-new (per spec §2) because RawDrawersTab's hit-click
// only opens a read-only slide-over — here a CHAPTER-source hit deep-links into the in-dock
// editor at that chapter (host.focusManuscriptUnit), which is what makes the result operable
// inside the studio. Non-chapter passages (chat/glossary) expand inline (their full text is
// already in the hit — no second fetch).

export interface SemanticSearchListProps {
  projectId: string | null;
  isProjectLoading: boolean;
  initialQuery?: string;
  /** Deep-link a chapter-source hit to the in-dock editor at that chapter. */
  onOpenChapter: (chapterId: string) => void;
}

const SOURCE_ICON: Record<string, typeof FileText> = {
  chapter: FileText,
  chat: MessageSquare,
  glossary: BookMarked,
};

export function SemanticSearchList({
  projectId,
  isProjectLoading,
  initialQuery,
  onOpenChapter,
}: SemanticSearchListProps) {
  const { t, i18n } = useTranslation('studio');
  const [input, setInput] = useState(initialQuery ?? '');
  const [expanded, setExpanded] = useState<string | null>(null);
  const query = useDebouncedValue(input, 300);

  const { hits, disabled, isFetching, error } = useDrawerSearch({
    project_id: projectId ?? '',
    query,
    language: i18n.language || undefined,
  });

  return (
    <div className="flex flex-col gap-3" data-testid="studio-semantic-search">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t('search.semantic.placeholder', { defaultValue: 'Search meaning across your lore…' })}
          aria-label={t('search.semantic.placeholder', { defaultValue: 'Search meaning across your lore…' })}
          data-testid="studio-semantic-input"
          className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
        />
      </div>

      {isProjectLoading ? (
        <p className="text-sm text-muted-foreground" data-testid="studio-semantic-loading-project">
          {t('search.semantic.loadingProject', { defaultValue: 'Loading…' })}
        </p>
      ) : projectId === null ? (
        <p className="text-sm text-muted-foreground" data-testid="studio-semantic-no-project">
          {t('search.semantic.noProject', {
            defaultValue: 'This book has no knowledge project yet — extract or build knowledge first.',
          })}
        </p>
      ) : error ? (
        <p className="text-sm text-destructive" role="alert" data-testid="studio-semantic-error">
          {t('search.semantic.error', { defaultValue: 'Semantic search is unavailable right now.' })}
        </p>
      ) : disabled ? (
        <p className="text-sm text-muted-foreground" data-testid="studio-semantic-hint">
          {t('search.semantic.hint', { defaultValue: 'Type at least 3 characters to search by meaning.' })}
        </p>
      ) : isFetching && hits.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="studio-semantic-searching">
          {t('search.semantic.searching', { defaultValue: 'Searching…' })}
        </p>
      ) : hits.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="studio-semantic-empty">
          {t('search.semantic.empty', { defaultValue: 'No passages match.' })}
        </p>
      ) : (
        <ul className="divide-y rounded-md border" data-testid="studio-semantic-results">
          {hits.map((hit) => {
            const Icon = SOURCE_ICON[hit.source_type] ?? FileText;
            const isChapter = hit.source_type === 'chapter';
            const isOpen = expanded === hit.id;
            return (
              <li key={hit.id} className="p-2.5" data-testid="studio-semantic-hit" data-source-type={hit.source_type}>
                <button
                  type="button"
                  onClick={() => (isChapter ? onOpenChapter(hit.source_id) : setExpanded(isOpen ? null : hit.id))}
                  className="flex w-full items-start gap-2 text-left"
                  data-testid={isChapter ? 'studio-semantic-open-chapter' : 'studio-semantic-expand'}
                >
                  <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <span className="uppercase tracking-wide">{hit.source_type}</span>
                      <span>· {Math.round(hit.raw_score * 100)}%</span>
                      {isChapter && (
                        <span className="text-primary">
                          {t('search.semantic.openChapter', { defaultValue: 'open →' })}
                        </span>
                      )}
                    </span>
                    <span className={`mt-0.5 block text-[12px] text-foreground/80 ${isOpen ? '' : 'line-clamp-2'}`}>
                      {hit.text}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
