// 13_glossary_panels.md A3/Phase B — the `glossary` dock panel: entity list/search/filter/bulk-
// actions, the first Glossary capability to become a real studio panel. Thin view over the SAME
// GlossaryEntityList used by the classic GlossaryTab page (DOCK-2 — no fork).
//
// Phase B (complete): the ontology/unknown/ai_suggestions/merge_candidates capabilities are now
// real sibling dock panels (GlossaryOntologyPanel, GlossaryUnknownPanel,
// GlossaryAiSuggestionsPanel, GlossaryMergeCandidatesPanel) — the temporary internal view-switch
// (DOCK-8 debt) this panel carried during Phase A is gone; `onOpenView` now does a real
// cross-panel jump via the host instead of local view state.
import { useQuery } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { GlossaryEntityList, type OtherGlossaryView } from '@/features/glossary/components/GlossaryEntityList';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

const PANEL_FOR_VIEW: Record<OtherGlossaryView, string> = {
  ontology: 'glossary-ontology',
  unknown: 'glossary-unknown',
  ai_suggestions: 'glossary-ai-suggestions',
  merge_candidates: 'glossary-merge-candidates',
};

export function GlossaryPanel(props: IDockviewPanelProps) {
  useStudioPanel('glossary', props.api, { mcpToolPrefixes: ['glossary_'] });
  const host = useStudioHost();
  const { bookId } = host;
  const { accessToken } = useAuth();

  // Book language/genre context — cosmetic-priority like StudioFrame's own book-title fetch;
  // the list renders fine before this resolves (bookOriginalLanguage/bookGenreTags are optional).
  const { data: book } = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId),
    enabled: !!accessToken,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div data-testid="studio-glossary-panel" className="h-full min-h-0 overflow-auto">
      <GlossaryEntityList
        bookId={bookId}
        bookGenreTags={book?.genre_tags ?? []}
        bookOriginalLanguage={book?.original_language ?? undefined}
        onOpenView={(view) => host.openPanel(PANEL_FOR_VIEW[view])}
      />
    </div>
  );
}
