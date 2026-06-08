import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, useLocation } from 'react-router-dom';

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname}{loc.search}</div>;
}

const searchMock = vi.fn();
const hybridMock = vi.fn();
vi.mock('../../api', () => ({
  rawSearchApi: {
    search: (...a: unknown[]) => searchMock(...a),
    searchHybrid: (...a: unknown[]) => hybridMock(...a),
  },
}));
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

import { RawSearchPanel } from '../RawSearchPanel';

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <RawSearchPanel bookId="book-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const _draft = {
  chapterId: 'cd', chapterTitle: 'Draft', sortOrder: 1, surface: 'draft',
  matchType: 'lexical', score: 1, snippet: 'draft prose', highlights: [[0, 3]],
  location: { blockIndex: 0, headingContext: null, charStart: 0, charEnd: 3 },
};
const _canon = {
  chapterId: 'cc', chapterTitle: null, sortOrder: 9, surface: 'canon',
  matchType: 'semantic', score: 0.9, snippet: 'canon prose', highlights: [],
  location: { chunkIndex: 0, headingContext: null, charStart: 0, charEnd: 0 },
};

beforeEach(() => {
  searchMock.mockReset();
  hybridMock.mockReset();
  searchMock.mockResolvedValue({ query: '', mode: 'lexical', results: [] });
  hybridMock.mockResolvedValue({ query: '', mode: 'hybrid', results: [] });
});

describe('RawSearchPanel', () => {
  it('shows the hint and searches nothing before a query is typed', () => {
    renderPanel();
    expect(screen.getByTestId('raw-search-hint')).toBeInTheDocument();
    expect(hybridMock).not.toHaveBeenCalled();
  });

  it('hybrid (default) renders mixed draft + canon results', async () => {
    hybridMock.mockResolvedValue({
      query: '乾坤圈', mode: 'hybrid', results: [_draft, _canon],
    });
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: '乾坤圈' } });
    await waitFor(() => expect(screen.getByTestId('raw-search-results')).toBeInTheDocument());
    expect(screen.getAllByTestId('raw-search-result')).toHaveLength(2);
    const surfaces = screen.getAllByTestId('raw-search-surface').map((n) => n.textContent);
    expect(surfaces).toEqual(expect.arrayContaining(['draft', 'canon']));
  });

  it('renders the degraded note when the response degrades a leg', async () => {
    hybridMock.mockResolvedValue({
      query: 'x', mode: 'hybrid', results: [_draft],
      degraded: { semantic: 'embed_unavailable' },
    });
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('raw-search-degraded')).toBeInTheDocument());
  });

  it('switching to lexical mode queries the book-service leg', async () => {
    searchMock.mockResolvedValue({ query: 'x', mode: 'lexical', results: [_draft] });
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: 'x' } });
    fireEvent.click(screen.getByTestId('raw-search-mode-lexical'));
    await waitFor(() => expect(searchMock).toHaveBeenCalled());
  });

  it('jumps to the chapter reader at the matched block on click (lexical)', async () => {
    hybridMock.mockResolvedValue({ query: 'x', mode: 'hybrid', results: [_draft] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <RawSearchPanel bookId="book-1" />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('raw-search-result')).toBeInTheDocument());
    fireEvent.click(within(screen.getByTestId('raw-search-result')).getByRole('button'));
    expect(screen.getByTestId('loc').textContent).toBe(
      '/books/book-1/chapters/cd/read?block=0',
    );
  });

  it('opens the chapter without ?block for a semantic hit', async () => {
    hybridMock.mockResolvedValue({ query: 'x', mode: 'hybrid', results: [_canon] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <RawSearchPanel bookId="book-1" />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByTestId('raw-search-result')).toBeInTheDocument());
    fireEvent.click(within(screen.getByTestId('raw-search-result')).getByRole('button'));
    expect(screen.getByTestId('loc').textContent).toBe('/books/book-1/chapters/cc/read');
  });

  // ── E6: granularity / K / relevance ────────────────────────────────

  it('defaults to Navigate (chapter) + limit 20', async () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: 'x' } });
    await waitFor(() =>
      expect(hybridMock).toHaveBeenCalledWith(
        'book-1', expect.objectContaining({ granularity: 'chapter', limit: 20 }), 'tok',
      ),
    );
  });

  it('switching to Mine queries with granularity=block', async () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: '乾' } });
    await waitFor(() => expect(hybridMock).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('raw-search-granularity-block'));
    // Mine ⇒ rerank off so it stays exhaustive (review-impl MED-1).
    await waitFor(() =>
      expect(hybridMock).toHaveBeenCalledWith(
        'book-1', expect.objectContaining({ granularity: 'block', rerank: false }), 'tok',
      ),
    );
  });

  it('Navigate (default) keeps rerank on', async () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: 'x' } });
    await waitFor(() =>
      expect(hybridMock).toHaveBeenCalledWith(
        'book-1', expect.objectContaining({ granularity: 'chapter', rerank: true }), 'tok',
      ),
    );
  });

  it('changing the K selector re-queries with the new limit', async () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: 'x' } });
    await waitFor(() => expect(hybridMock).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId('raw-search-limit'), { target: { value: '50' } });
    await waitFor(() =>
      expect(hybridMock).toHaveBeenCalledWith(
        'book-1', expect.objectContaining({ limit: 50 }), 'tok',
      ),
    );
  });

  it('renders the relevance bar for a scored hit', async () => {
    hybridMock.mockResolvedValue({
      query: 'x', mode: 'hybrid', results: [{ ..._canon, relevance: 0.97 }],
    });
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: 'x' } });
    await waitFor(() =>
      expect(screen.getByTestId('raw-search-relevance')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('raw-search-relevance').getAttribute('title')).toBe('97%');
  });
});
