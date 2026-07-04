// 13_glossary_panels.md A3 — the `glossary` dock panel: entity list/search/filter/bulk-actions,
// the first Glossary capability to become a real studio panel. Thin view over the SAME
// GlossaryEntityList used by the classic GlossaryTab page (DOCK-2 — no fork).
//
// Phase-B debt (tracked, NOT silent): ontology/unknown/ai_suggestions/merge_candidates are not
// yet their own dock panels, so this panel temporarily reproduces GlossaryTab's internal
// view-switch for those four (a DOCK-8 exception the spec explicitly schedules Phase B to
// remove, one panel at a time — see 13_glossary_panels.md Phase B table).
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useEntityKinds } from '@/features/glossary/hooks/useEntityKinds';
import { GlossaryEntityList, type OtherGlossaryView } from '@/features/glossary/components/GlossaryEntityList';
import { OntologyShell } from '@/features/glossary/components/tiering/OntologyShell';
import { UnknownEntitiesPanel } from '@/features/glossary/components/UnknownEntitiesPanel';
import { AiSuggestionsPanel } from '@/features/glossary/components/AiSuggestionsPanel';
import { MergeCandidatePanel } from '@/features/glossary/components/MergeCandidatePanel';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

type GlossaryView = 'entities' | OtherGlossaryView;

export function GlossaryPanel(props: IDockviewPanelProps) {
  useStudioPanel('glossary', props.api, { mcpToolPrefixes: ['glossary_'] });
  const host = useStudioHost();
  const { bookId } = host;
  const { accessToken } = useAuth();
  const [view, setView] = useState<GlossaryView>('entities');
  // System kinds — only the 'unknown' branch needs them (reassign an unrecognized entity to a
  // real kind). The entity list's OWN kind filter is book-scoped, fetched inside
  // GlossaryEntityList via useBookOntology — a different, book-tier query (D-GKA-FILTER-BOOKKINDS).
  const { kinds: systemKinds } = useEntityKinds();

  // Book language/genre context — cosmetic-priority like StudioFrame's own book-title fetch;
  // the list renders fine before this resolves (bookOriginalLanguage/bookGenreTags are optional).
  const { data: book } = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId),
    enabled: !!accessToken,
    staleTime: 5 * 60 * 1000,
  });

  if (view === 'ontology') {
    return <OntologyShell bookId={bookId} onClose={() => setView('entities')} />;
  }
  if (view === 'unknown') {
    return <UnknownEntitiesPanel bookId={bookId} kinds={systemKinds} onClose={() => setView('entities')} />;
  }
  if (view === 'ai_suggestions') {
    return <AiSuggestionsPanel bookId={bookId} onClose={() => setView('entities')} />;
  }
  if (view === 'merge_candidates') {
    return <MergeCandidatePanel bookId={bookId} onClose={() => setView('entities')} />;
  }

  return (
    <div data-testid="studio-glossary-panel" className="h-full min-h-0 overflow-auto">
      <GlossaryEntityList
        bookId={bookId}
        bookGenreTags={book?.genre_tags ?? []}
        bookOriginalLanguage={book?.original_language ?? undefined}
        onOpenView={setView}
      />
    </div>
  );
}
