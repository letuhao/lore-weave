import { useState } from 'react';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { GlossaryEntityList, type OtherGlossaryView } from '@/features/glossary/components/GlossaryEntityList';
import { useQuery } from '@tanstack/react-query';
import { OntologyShell } from '@/features/glossary/components/tiering/OntologyShell';
import { UnknownEntitiesPanel } from '@/features/glossary/components/UnknownEntitiesPanel';
import { AiSuggestionsPanel } from '@/features/glossary/components/AiSuggestionsPanel';
import { MergeCandidatePanel } from '@/features/glossary/components/MergeCandidatePanel';

type GlossaryView = 'entities' | OtherGlossaryView;

/** The classic route/page surface (13_glossary_panels.md A3 — stays per Wave-1 precedent:
 * existing pages/routes are multi-device entry points, not replaced by the studio dock panel).
 * The entity-list capability itself lives in GlossaryEntityList, shared with GlossaryPanel
 * (the new dock panel) so the ~500 lines of list/filter/bulk logic aren't forked (DOCK-2). This
 * shell only owns the `view` switch across entities/ontology/unknown/ai_suggestions/merge_candidates
 * — unchanged from before the extraction. */
export function GlossaryTab({ bookId, bookGenreTags = [], bookOriginalLanguage }: { bookId: string; bookGenreTags?: string[]; bookOriginalLanguage?: string }) {
  const { accessToken } = useAuth();
  const [view, setView] = useState<GlossaryView>('entities');

  // System kinds — needed by the orthogonal E3 unknown-review flow (reassign an unrecognized
  // entity to a kind in the system taxonomy). NOT used for the entity filter (book-scoped,
  // fetched inside GlossaryEntityList via useBookOntology).
  const { data: systemKinds = [] } = useQuery({
    queryKey: ['glossary-kinds'],
    queryFn: () => glossaryApi.getKinds(accessToken!),
    enabled: !!accessToken,
    staleTime: 10 * 60 * 1000,
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
    <GlossaryEntityList
      bookId={bookId}
      bookGenreTags={bookGenreTags}
      bookOriginalLanguage={bookOriginalLanguage}
      onOpenView={setView}
    />
  );
}
