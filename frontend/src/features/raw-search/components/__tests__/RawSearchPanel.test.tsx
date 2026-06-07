import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

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
});
