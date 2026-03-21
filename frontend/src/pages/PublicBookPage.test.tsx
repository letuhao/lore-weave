import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PublicBookPage } from './PublicBookPage';

const getCatalogBook = vi.fn();
const listCatalogChapters = vi.fn();
const getCatalogChapter = vi.fn();

vi.mock('@/features/books/api', () => ({
  booksApi: {
    getCatalogBook: (...args: unknown[]) => getCatalogBook(...args),
    listCatalogChapters: (...args: unknown[]) => listCatalogChapters(...args),
    getCatalogChapter: (...args: unknown[]) => getCatalogChapter(...args),
  },
}));

describe('PublicBookPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  function renderPage() {
    return render(
      <MemoryRouter initialEntries={['/browse/book-1']}>
        <Routes>
          <Route path="/browse/:bookId" element={<PublicBookPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('loads public book and chapter list', async () => {
    getCatalogBook.mockResolvedValueOnce({
      book_id: 'book-1',
      title: 'Public A',
      summary_excerpt: 'summary',
      original_language: 'en',
    });
    listCatalogChapters.mockResolvedValueOnce({
      items: [{ chapter_id: 'c1', title: 'Chapter 1', sort_order: 1, original_language: 'en' }],
      total: 1,
    });

    renderPage();

    expect(await screen.findByText('Public A')).toBeInTheDocument();
    expect(await screen.findByText(/Chapter 1/)).toBeInTheDocument();
  });

  it('loads chapter detail on chapter click', async () => {
    getCatalogBook.mockResolvedValue({
      book_id: 'book-1',
      title: 'Public A',
      summary_excerpt: 'summary',
      original_language: 'en',
    });
    listCatalogChapters.mockResolvedValue({
      items: [{ chapter_id: 'c1', title: 'Chapter 1', sort_order: 1, original_language: 'en' }],
      total: 1,
    });
    getCatalogChapter.mockResolvedValueOnce({
      chapter_id: 'c1',
      title: 'Chapter 1',
      sort_order: 1,
      original_language: 'en',
      body: 'public body',
    });

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Chapter 1/ }));

    await waitFor(() => expect(getCatalogChapter).toHaveBeenCalledWith('book-1', 'c1'));
    expect(await screen.findByText('public body')).toBeInTheDocument();
  });
});
