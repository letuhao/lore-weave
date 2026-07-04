// 15_chapter_browser.md B2 — ChapterBrowserContentView tests. Mirrors
// raw-search/components/__tests__/RawSearchPanel.test.tsx's mocking shape (same underlying
// hooks, DOCK-2 reuse) but asserts the Chapter Browser's OWN render (snippet-card density) and,
// crucially, that "Jump to source" calls host.openPanel('book-reader', ...) — NOT navigate()
// (DOCK-7). No MemoryRouter anywhere in this file; a stray useNavigate/useParams/<Link> in the
// component under test would fail loudly (no router context provided).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StudioHostProvider, useStudioHost } from '../../host/StudioHostProvider';
import type { StudioHost } from '../../host/StudioHostProvider';

const searchMock = vi.fn();
const hybridMock = vi.fn();
const indexDraftsMock = vi.fn();
vi.mock('@/features/raw-search/api', () => ({
  rawSearchApi: {
    search: (...a: unknown[]) => searchMock(...a),
    searchHybrid: (...a: unknown[]) => hybridMock(...a),
    indexDrafts: (...a: unknown[]) => indexDraftsMock(...a),
  },
}));
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));
let _ownerId = 'u1';
vi.mock('@/features/books/api', () => ({
  booksApi: {
    getBook: () => Promise.resolve({ owner_user_id: _ownerId }),
  },
}));

import { ChapterBrowserContentView } from '../ChapterBrowserContentView';

let hostRef: StudioHost | null = null;
function HostProbe() {
  hostRef = useStudioHost();
  return null;
}

function renderView(bookId = 'book-1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudioHostProvider bookId={bookId}>
        <HostProbe />
        <ChapterBrowserContentView bookId={bookId} />
      </StudioHostProvider>
    </QueryClientProvider>,
  );
}

const _lexicalHit = {
  chapterId: 'cd', chapterTitle: "The Regent's Gambit", sortOrder: 41, surface: 'draft',
  matchType: 'lexical', score: 1, relevance: 0.8, snippet: 'the crimson banner falls tonight',
  highlights: [[4, 11]],
  location: { blockIndex: 14, headingContext: 'The war council', charStart: 4, charEnd: 11 },
};
const _semanticHit = {
  chapterId: 'cc', chapterTitle: null, sortOrder: 9, surface: 'canon',
  matchType: 'semantic', score: 0.9, snippet: 'canon prose about the crimson banner',
  highlights: [],
  location: { chunkIndex: 3, headingContext: null, charStart: 0, charEnd: 0 },
};

beforeEach(() => {
  searchMock.mockReset();
  hybridMock.mockReset();
  indexDraftsMock.mockReset();
  _ownerId = 'u1';
  hostRef = null;
  searchMock.mockResolvedValue({ query: '', mode: 'lexical', results: [] });
  hybridMock.mockResolvedValue({ query: '', mode: 'hybrid', results: [] });
  indexDraftsMock.mockResolvedValue({ indexed: 2, skipped: 0, chapters: 2 });
});

describe('ChapterBrowserContentView', () => {
  it('shows the hint and searches nothing before a query is typed', () => {
    renderView();
    expect(screen.getByTestId('chapter-browser-content-hint')).toBeInTheDocument();
    expect(hybridMock).not.toHaveBeenCalled();
  });

  it('renders a snippet card per hit with title, breadcrumb, surface badge, and highlighted snippet', async () => {
    hybridMock.mockResolvedValue({ query: 'crimson', mode: 'hybrid', results: [_lexicalHit] });
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'crimson' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-content-results')).toBeInTheDocument());
    const card = screen.getByTestId('chapter-browser-snippet-card');
    expect(within(card).getByTestId('chapter-browser-snippet-title').textContent).toContain("The Regent's Gambit");
    expect(within(card).getByTestId('chapter-browser-snippet-crumb').textContent).toContain('The war council');
    expect(within(card).getByTestId('chapter-browser-snippet-surface').textContent).toBe('draft');
    expect(within(card).getByText('crimson').tagName).toBe('MARK');
    expect(within(card).getByTestId('chapter-browser-snippet-body').textContent).toBe('the crimson banner falls tonight');
  });

  it('shows the relevance meter with the calibrated percentage', async () => {
    hybridMock.mockResolvedValue({ query: 'x', mode: 'hybrid', results: [_lexicalHit] });
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-snippet-relevance')).toBeInTheDocument());
    expect(screen.getByTestId('chapter-browser-snippet-relevance').getAttribute('title')).toBe('80%');
  });

  it('shows the block position footer for a lexical (block-indexed) hit', async () => {
    // Repo test convention: the global react-i18next mock (vitest.setup.ts) returns the KEY,
    // not a looked-up+interpolated English string (it never loads the real JSON resources) —
    // assert on the key + a distinct block-vs-passage KEY, not literal English copy.
    hybridMock.mockResolvedValue({ query: 'x', mode: 'hybrid', results: [_lexicalHit] });
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-snippet-position')).toBeInTheDocument());
    expect(screen.getByTestId('chapter-browser-snippet-position').textContent).toBe('content_view.block_position');
  });

  it('shows the passage position footer (a distinct key from block position) for a semantic (chunk-indexed) hit with no title', async () => {
    hybridMock.mockResolvedValue({ query: 'x', mode: 'hybrid', results: [_semanticHit] });
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-snippet-position')).toBeInTheDocument());
    expect(screen.getByTestId('chapter-browser-snippet-position').textContent).toBe('content_view.passage_position');
    // No chapterTitle on this hit ⇒ falls back to just the "Ch. N" key (no " — title" suffix).
    expect(screen.getByTestId('chapter-browser-snippet-title').textContent).toBe('content_view.chapter_label');
  });

  it('switching to lexical mode queries the book-service leg', async () => {
    searchMock.mockResolvedValue({ query: 'x', mode: 'lexical', results: [_lexicalHit] });
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    fireEvent.click(screen.getByTestId('chapter-browser-content-mode-lexical'));
    await waitFor(() => expect(searchMock).toHaveBeenCalled());
  });

  it('switching granularity to block re-queries with granularity=block', async () => {
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(hybridMock).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('chapter-browser-content-granularity-block'));
    await waitFor(() =>
      expect(hybridMock).toHaveBeenCalledWith(
        'book-1', expect.objectContaining({ granularity: 'block' }), 'tok',
      ),
    );
  });

  it('changing the limit selector re-queries with the new limit', async () => {
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(hybridMock).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('chapter-browser-content-limit'), { target: { value: '50' } });
    await waitFor(() =>
      expect(hybridMock).toHaveBeenCalledWith(
        'book-1', expect.objectContaining({ limit: 50 }), 'tok',
      ),
    );
  });

  it('owner sees the surface toggle and index-drafts action', async () => {
    renderView();
    await waitFor(() => expect(screen.getByTestId('chapter-browser-content-surface-all')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('chapter-browser-content-index-drafts'));
    await waitFor(() => expect(indexDraftsMock).toHaveBeenCalledWith('book-1', 'tok'));
    await waitFor(() =>
      expect(screen.getByTestId('chapter-browser-content-index-drafts-result')).toBeInTheDocument(),
    );
  });

  it('a collaborator (non-owner) sees neither the surface toggle nor index-drafts', async () => {
    _ownerId = 'someone-else';
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(hybridMock).toHaveBeenCalled());
    expect(screen.queryByTestId('chapter-browser-content-surface-all')).not.toBeInTheDocument();
    expect(screen.queryByTestId('chapter-browser-content-index-drafts')).not.toBeInTheDocument();
    expect(hybridMock).toHaveBeenCalledWith(
      'book-1', expect.objectContaining({ surface: 'canon' }), 'tok',
    );
  });

  it('renders the degraded note when a leg degrades', async () => {
    hybridMock.mockResolvedValue({
      query: 'x', mode: 'hybrid', results: [_lexicalHit], degraded: { semantic: 'embed_unavailable' },
    });
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-content-degraded')).toBeInTheDocument());
  });

  it('shows the empty state when a query returns no results', async () => {
    hybridMock.mockResolvedValue({ query: 'zzz', mode: 'hybrid', results: [] });
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'zzz' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-content-empty')).toBeInTheDocument());
  });

  it('shows the error state when the search fails', async () => {
    hybridMock.mockRejectedValue(new Error('boom'));
    renderView();
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-content-error')).toBeInTheDocument());
  });

  // ── DOCK-7: jump-to-source must call host.openPanel, never navigate ──────

  it('"Jump to source" calls host.openPanel("book-reader", {params: {bookId, chapterId}})', async () => {
    hybridMock.mockResolvedValue({ query: 'x', mode: 'hybrid', results: [_lexicalHit] });
    renderView('book-1');
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-snippet-card')).toBeInTheDocument());
    const openPanelSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByTestId('chapter-browser-snippet-jump'));
    expect(openPanelSpy).toHaveBeenCalledWith('book-reader', { params: { bookId: 'book-1', chapterId: 'cd' } });
  });

  it('a semantic hit jumps with the same {bookId, chapterId} shape (no block param available)', async () => {
    hybridMock.mockResolvedValue({ query: 'x', mode: 'hybrid', results: [_semanticHit] });
    renderView('book-1');
    fireEvent.change(screen.getByTestId('chapter-browser-content-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-snippet-card')).toBeInTheDocument());
    const openPanelSpy = vi.spyOn(hostRef!, 'openPanel');
    fireEvent.click(screen.getByTestId('chapter-browser-snippet-jump'));
    expect(openPanelSpy).toHaveBeenCalledWith('book-reader', { params: { bookId: 'book-1', chapterId: 'cc' } });
  });
});
