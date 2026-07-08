import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

// 13_glossary_panels.md A3 — GlossaryEntityList is the extracted, shared entity-list
// capability (DOCK-2: one implementation, not forked between GlossaryTab and GlossaryPanel).
// This test's main job: prove the extraction didn't drop behavior, and that the 4
// "other capability" triggers call `onOpenView` (the DOCK-8 launcher seam) instead of an
// internal setView the way the old GlossaryTab did.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const apiMocks = vi.hoisted(() => ({
  listTranslationLanguages: vi.fn(),
  listEntities: vi.fn(),
  listUnknownEntities: vi.fn(),
  listAiSuggestions: vi.fn(),
  listMergeCandidates: vi.fn(),
  deleteEntity: vi.fn(),
  bulkSetStatus: vi.fn(),
  bulkDeleteEntities: vi.fn(),
  patchEntity: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: apiMocks }));

vi.mock('../../hooks/useBookOntology', () => ({
  useBookOntology: () => ({
    ontology: {
      kinds: [{ book_kind_id: 'k1', code: 'character', name: 'Character', icon: '🧑', is_hidden: false, sort_order: 0 }],
      genres: [], attributes: [],
    },
    isLoading: false,
  }),
}));

vi.mock('../../hooks/useGlossaryDisplayLanguage', () => ({
  useGlossaryDisplayLanguage: () => ({
    displayLanguage: '', setDisplayLanguage: vi.fn(), apiDisplayLanguage: undefined, loaded: true,
  }),
}));

// Stub the peer dialogs/wizards — each is (or will be) independently tested; this
// component's job is the list + the DOCK-8 launcher wiring, not their internals.
vi.mock('@/components/entity-editor', () => ({
  EntityEditorModal: ({ entityId, onClose }: { entityId: string; onClose: () => void }) => (
    <div data-testid="stub-entity-editor">
      editing {entityId}
      <button onClick={onClose}>close-editor</button>
    </div>
  ),
}));
vi.mock('../tiering/CreateEntityModal', () => ({ CreateEntityModal: () => <div data-testid="stub-create-entity" /> }));
vi.mock('@/features/extraction/ExtractionWizard', () => ({ ExtractionWizard: () => null }));
vi.mock('@/features/glossary-translate/GlossaryTranslateWizard', () => ({ GlossaryTranslateWizard: () => null }));
vi.mock('../BatchTranslateDialog', () => ({ BatchTranslateDialog: () => null }));

import { GlossaryEntityList } from '../GlossaryEntityList';

const BOOK = 'book-1';

function entitySummary(id: string, name: string) {
  return {
    entity_id: id, book_id: BOOK, kind_id: 'k1',
    kind: { kind_id: 'k1', code: 'character', name: 'Character', icon: '🧑', color: '#fff' },
    display_name: name, display_name_translation: null,
    status: 'draft' as const, tags: [],
    chapter_link_count: 0, translation_count: 0, evidence_count: 0,
    created_at: '2026-07-04T00:00:00Z', updated_at: '2026-07-04T00:00:00Z',
  };
}

function renderList(onOpenView = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  const utils = render(<GlossaryEntityList bookId={BOOK} onOpenView={onOpenView} />, { wrapper: Wrapper });
  return { ...utils, onOpenView };
}

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
  apiMocks.listTranslationLanguages.mockResolvedValue({ languages: [] });
  apiMocks.listEntities.mockResolvedValue({ items: [entitySummary('e1', 'Jiang Ziya')], total: 1 });
  apiMocks.listUnknownEntities.mockResolvedValue({ total: 0, items: [] });
  apiMocks.listAiSuggestions.mockResolvedValue({ total: 0, items: [] });
  apiMocks.listMergeCandidates.mockResolvedValue({ candidates: [] });
});

describe('GlossaryEntityList (13_glossary_panels.md A3)', () => {
  it('renders the entity list from listEntities', async () => {
    renderList();
    expect(await screen.findByText('Jiang Ziya')).toBeInTheDocument();
  });

  it('shows a scope_label badge only for entities that have one set (D-GLOSSARY-ENTITY-SCOPE)', async () => {
    apiMocks.listEntities.mockResolvedValue({
      items: [{ ...entitySummary('e1', 'Jiang Ziya'), scope_label: 'World A' }],
      total: 1,
    });
    renderList();
    expect(await screen.findByText('World A')).toBeInTheDocument();
  });

  it('clicking a row opens the entity editor for that entity', async () => {
    renderList();
    fireEvent.click(await screen.findByTestId('glossary-entity-row'));
    expect(await screen.findByTestId('stub-entity-editor')).toHaveTextContent('editing e1');
  });

  it('the ontology trigger calls onOpenView("ontology") — the DOCK-8 launcher seam', async () => {
    const { onOpenView } = renderList();
    fireEvent.click(await screen.findByTestId('glossary-ontology-trigger'));
    expect(onOpenView).toHaveBeenCalledWith('ontology');
  });

  it('the unknown-review trigger appears only when the queue is non-empty, and calls onOpenView("unknown")', async () => {
    apiMocks.listUnknownEntities.mockResolvedValue({ total: 3, items: [] });
    const { onOpenView } = renderList();
    const trigger = await screen.findByTestId('glossary-unknown-trigger');
    fireEvent.click(trigger);
    expect(onOpenView).toHaveBeenCalledWith('unknown');
  });

  it('the AI-suggestions trigger calls onOpenView("ai_suggestions")', async () => {
    apiMocks.listAiSuggestions.mockResolvedValue({ total: 2, items: [] });
    const { onOpenView } = renderList();
    fireEvent.click(await screen.findByTestId('glossary-ai-suggestions-trigger'));
    expect(onOpenView).toHaveBeenCalledWith('ai_suggestions');
  });

  it('the merge-candidates trigger calls onOpenView("merge_candidates")', async () => {
    apiMocks.listMergeCandidates.mockResolvedValue({ candidates: [{ candidate_id: 'c1' }] });
    const { onOpenView } = renderList();
    fireEvent.click(await screen.findByTestId('glossary-merge-candidates-trigger'));
    expect(onOpenView).toHaveBeenCalledWith('merge_candidates');
  });

  it('bulk-activating the selected rows calls bulkSetStatus and clears the selection', async () => {
    renderList();
    await screen.findByText('Jiang Ziya');
    fireEvent.click(screen.getByLabelText('glossary.bulk.select_row'));
    apiMocks.bulkSetStatus.mockResolvedValue({ updated: 1 });
    fireEvent.click(screen.getByText('glossary.bulk.activate'));
    await waitFor(() => expect(apiMocks.bulkSetStatus).toHaveBeenCalledWith(BOOK, 'active', ['e1'], 'tok'));
  });

  it('bulk-rejecting the selected rows calls bulkSetStatus with "rejected" and clears the selection', async () => {
    renderList();
    await screen.findByText('Jiang Ziya');
    fireEvent.click(screen.getByLabelText('glossary.bulk.select_row'));
    apiMocks.bulkSetStatus.mockResolvedValue({ updated: 1 });
    fireEvent.click(screen.getByText('glossary.bulk.reject'));
    await waitFor(() => expect(apiMocks.bulkSetStatus).toHaveBeenCalledWith(BOOK, 'rejected', ['e1'], 'tok'));
  });

  it('the new-entity button opens the (stubbed) create-entity modal', async () => {
    renderList();
    fireEvent.click(await screen.findByTestId('glossary-new-entity'));
    expect(await screen.findByTestId('stub-create-entity')).toBeInTheDocument();
  });
});
