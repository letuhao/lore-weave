import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

const searchMock = vi.fn();
vi.mock('../../api', () => ({
  rawSearchApi: { search: (...a: unknown[]) => searchMock(...a) },
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

beforeEach(() => {
  searchMock.mockReset();
  searchMock.mockResolvedValue({ query: '', mode: 'lexical', results: [] });
});

describe('RawSearchPanel', () => {
  it('shows the hint and does not search before a query is typed', () => {
    renderPanel();
    expect(screen.getByTestId('raw-search-hint')).toBeInTheDocument();
    expect(searchMock).not.toHaveBeenCalled();
  });

  it('searches on input and renders draft-labelled results', async () => {
    const hit = {
      chapterId: 'c1', chapterTitle: 'Ch1', sortOrder: 1,
      surface: 'draft', matchType: 'lexical', score: 1,
      snippet: '乾坤圈是法宝', highlights: [[0, 3]],
      location: { blockIndex: 0, headingContext: null, charStart: 0, charEnd: 3 },
    };
    searchMock.mockResolvedValue({ query: '乾坤圈', mode: 'lexical', results: [hit] });
    renderPanel();
    fireEvent.change(screen.getByTestId('raw-search-input'), { target: { value: '乾坤圈' } });
    await waitFor(() => expect(screen.getByTestId('raw-search-results')).toBeInTheDocument());
    expect(screen.getAllByTestId('raw-search-result')).toHaveLength(1);
    expect(screen.getByTestId('raw-search-surface').textContent).toBe('draft');
  });
});
