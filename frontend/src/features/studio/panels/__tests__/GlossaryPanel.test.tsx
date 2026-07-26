// 13_glossary_panels.md A3/Phase B — GlossaryPanel: resolves book_id from the host, self-titles,
// registers, fetches book language/genre for the entity list, and routes the four "other
// capability" launchers to their REAL sibling dock panels (Phase B — the temporary internal
// view-switch from Phase A is gone). Stubs the heavy children so this test stays about the
// panel's OWN wiring, not GlossaryEntityList's internals (separately tested).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const getBook = vi.fn();
vi.mock('@/features/books/api', () => ({ booksApi: { getBook: (...a: unknown[]) => getBook(...a) } }));

vi.mock('@/features/glossary/components/GlossaryEntityList', () => ({
  GlossaryEntityList: ({ bookId, bookOriginalLanguage, onOpenView }: { bookId: string; bookOriginalLanguage?: string; onOpenView: (v: string) => void }) => (
    <div data-testid="stub-entity-list" data-book={bookId} data-lang={bookOriginalLanguage ?? ''}>
      <button onClick={() => onOpenView('ontology')}>open-ontology</button>
      <button onClick={() => onOpenView('unknown')}>open-unknown</button>
      <button onClick={() => onOpenView('ai_suggestions')}>open-ai-suggestions</button>
      <button onClick={() => onOpenView('merge_candidates')}>open-merge-candidates</button>
    </div>
  ),
}));

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

  it.each([
    ['open-ontology', 'glossary-ontology'],
    ['open-unknown', 'glossary-unknown'],
    ['open-ai-suggestions', 'glossary-ai-suggestions'],
    ['open-merge-candidates', 'glossary-merge-candidates'],
  ])('%s routes to the REAL sibling panel %s via host.openPanel (Phase B — no more internal view-switch)', async (trigger, panelId) => {
    withHost('b1', <GlossaryPanel {...dockProps()} />);
    const openPanelSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(await screen.findByText(trigger));
    expect(openPanelSpy).toHaveBeenCalledWith(panelId);
  });
});
