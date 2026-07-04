// 13_glossary_panels.md A3 — GlossaryPanel: resolves book_id from the host, self-titles,
// registers, fetches book language/genre for the entity list, and (Phase-B debt, tracked)
// temporarily reproduces the ontology/unknown/ai_suggestions/merge_candidates view-swap
// GlossaryTab still owns for its own route. Stubs the heavy children so this test stays
// about the panel's OWN wiring, not GlossaryEntityList's internals (separately tested).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const getBook = vi.fn();
vi.mock('@/features/books/api', () => ({ booksApi: { getBook: (...a: unknown[]) => getBook(...a) } }));

vi.mock('@/features/glossary/hooks/useEntityKinds', () => ({
  useEntityKinds: () => ({ kinds: [{ kind_id: 'k1', code: 'character', name: 'Character' }], isLoading: false, error: '' }),
}));

vi.mock('@/features/glossary/components/GlossaryEntityList', () => ({
  GlossaryEntityList: ({ bookId, bookOriginalLanguage, onOpenView }: { bookId: string; bookOriginalLanguage?: string; onOpenView: (v: string) => void }) => (
    <div data-testid="stub-entity-list" data-book={bookId} data-lang={bookOriginalLanguage ?? ''}>
      <button onClick={() => onOpenView('ontology')}>open-ontology</button>
      <button onClick={() => onOpenView('unknown')}>open-unknown</button>
    </div>
  ),
}));
vi.mock('@/features/glossary/components/tiering/OntologyShell', () => ({
  OntologyShell: ({ onClose }: { onClose: () => void }) => <div data-testid="stub-ontology"><button onClick={onClose}>back</button></div>,
}));
vi.mock('@/features/glossary/components/UnknownEntitiesPanel', () => ({
  UnknownEntitiesPanel: ({ kinds }: { kinds: Array<{ code: string }> }) => <div data-testid="stub-unknown" data-kinds={kinds.length} />,
}));
vi.mock('@/features/glossary/components/AiSuggestionsPanel', () => ({ AiSuggestionsPanel: () => <div data-testid="stub-ai-suggestions" /> }));
vi.mock('@/features/glossary/components/MergeCandidatePanel', () => ({ MergeCandidatePanel: () => <div data-testid="stub-merge-candidates" /> }));

import { GlossaryPanel } from '../GlossaryPanel';

let hostRef: StudioHost | null = null;
function HostProbe() { hostRef = useStudioHost(); return null; }

function dockProps() {
  return { api: { setTitle: vi.fn() } } as unknown as IDockviewPanelProps;
}

function withHost(bookId: string, ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId={bookId}><HostProbe />{ui}</StudioHostProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hostRef = null;
  getBook.mockReset();
  getBook.mockResolvedValue({ book_id: 'b1', title: 'Fengshen', original_language: 'zh', genre_tags: ['xianxia'] });
});

describe('GlossaryPanel', () => {
  it('resolves book_id from the host and renders the entity list once book data loads', async () => {
    const props = dockProps();
    withHost('b1', <GlossaryPanel {...props} />);
    const stub = await screen.findByTestId('stub-entity-list');
    expect(stub.getAttribute('data-book')).toBe('b1');
    await waitFor(() => expect(stub.getAttribute('data-lang')).toBe('zh'));
    expect(props.api.setTitle).toHaveBeenCalled();
  });

  it('registers with the host as an openable studio tool tagged with the glossary_ MCP prefix', () => {
    withHost('b1', <GlossaryPanel {...dockProps()} />);
    expect(hostRef!.getRegisteredTool('glossary')).not.toBeNull();
    expect(hostRef!.getRegisteredTool('glossary')!.commandId).toBe('studio.openPanel.glossary');
    expect(hostRef!.getRegisteredTool('glossary')!.mcpToolPrefixes).toEqual(['glossary_']);
  });

  it('the ontology launcher swaps to the (Phase-B-temporary) internal ontology view and back', async () => {
    withHost('b1', <GlossaryPanel {...dockProps()} />);
    fireEvent.click(await screen.findByText('open-ontology'));
    expect(await screen.findByTestId('stub-ontology')).toBeInTheDocument();
    fireEvent.click(screen.getByText('back'));
    expect(await screen.findByTestId('stub-entity-list')).toBeInTheDocument();
  });

  it('the unknown-review launcher swaps to the unknown view, passing system kinds through', async () => {
    withHost('b1', <GlossaryPanel {...dockProps()} />);
    fireEvent.click(await screen.findByText('open-unknown'));
    const stub = await screen.findByTestId('stub-unknown');
    expect(stub.getAttribute('data-kinds')).toBe('1');
  });
});
