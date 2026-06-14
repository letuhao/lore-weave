import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listChapters = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { listChapters: (...a: unknown[]) => listChapters(...a) },
}));

import { ChapterListBrowser } from '../ChapterListBrowser';

function chap(id: string, order: number, title: string) {
  return { chapter_id: id, book_id: 'b', original_filename: `${order}.txt`, original_language: 'zh', content_type: 'text', byte_size: 1, sort_order: order, lifecycle_state: 'active', title };
}

function renderBrowser(props: Record<string, unknown>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChapterListBrowser bookId="b" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listChapters.mockReset();
  listChapters.mockResolvedValue({ items: [chap('c1', 1, 'Alpha'), chap('c2', 2, 'Beta')], total: 120 });
});

describe('ChapterListBrowser', () => {
  it('renders chapters + the range from total', async () => {
    renderBrowser({});
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    expect(screen.getByText('Alpha')).toBeTruthy();
    expect(screen.getByTestId('chapter-browser-range')).toBeTruthy();
  });

  it('multi mode: toggling a checkbox reports the selection', async () => {
    const onSelectionChange = vi.fn();
    renderBrowser({ selectionMode: 'multi', selectedIds: new Set<string>(), onSelectionChange });
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    const checkboxes = screen.getAllByLabelText('chapterBrowser.select_row');
    fireEvent.click(checkboxes[0]);
    expect(onSelectionChange).toHaveBeenCalled();
    const arg = onSelectionChange.mock.calls[0][0] as Set<string>;
    expect(arg.has('c1')).toBe(true);
  });

  it('single mode: row click fires onRowClick', async () => {
    const onRowClick = vi.fn();
    renderBrowser({ selectionMode: 'single', selectedIds: new Set<string>(), onSelectionChange: vi.fn(), onRowClick });
    await waitFor(() => expect(screen.getAllByTestId('chapter-browser-row').length).toBe(2));
    fireEvent.click(screen.getByText('Beta'));
    expect(onRowClick).toHaveBeenCalledWith(expect.objectContaining({ chapter_id: 'c2' }));
  });

  it('passes editorial_status + lifecycle filters to the query', async () => {
    renderBrowser({ editorialStatus: 'published', lifecycle: 'active' });
    await waitFor(() => expect(listChapters).toHaveBeenCalled());
    const params = listChapters.mock.calls[0][2];
    expect(params.editorial_status).toBe('published');
    expect(params.lifecycle_state).toBe('active');
  });

  it('debounced search reaches the query as q', async () => {
    renderBrowser({ enableSearch: true });
    await waitFor(() => expect(screen.getByTestId('chapter-browser-search')).toBeTruthy());
    fireEvent.change(screen.getByTestId('chapter-browser-search'), { target: { value: 'wang' } });
    await waitFor(() => {
      const called = listChapters.mock.calls.some((c) => c[2]?.q === 'wang');
      expect(called).toBe(true);
    }, { timeout: 1000 });
  });
});
