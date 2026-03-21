import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { UnlistedPage } from './UnlistedPage';

const getUnlisted = vi.fn();
const listUnlistedChapters = vi.fn();
const getUnlistedChapter = vi.fn();

vi.mock('@/features/books/api', () => ({
  booksApi: {
    getUnlisted: (...args: unknown[]) => getUnlisted(...args),
    listUnlistedChapters: (...args: unknown[]) => listUnlistedChapters(...args),
    getUnlistedChapter: (...args: unknown[]) => getUnlistedChapter(...args),
  },
}));

describe('UnlistedPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  function renderPage() {
    return render(
      <MemoryRouter initialEntries={['/s/token-abc']}>
        <Routes>
          <Route path="/s/:accessToken" element={<UnlistedPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('loads unlisted payload and chapter list', async () => {
    getUnlisted.mockResolvedValueOnce({
      book_id: 'book-1',
      title: 'Unlisted A',
      summary_excerpt: 'summary',
      original_language: 'vi',
    });
    listUnlistedChapters.mockResolvedValueOnce({
      items: [{ chapter_id: 'c1', title: 'Chapter 1', sort_order: 1, original_language: 'vi' }],
      total: 1,
    });

    renderPage();

    expect(await screen.findByText('Unlisted A')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Chapter 1/ })).toBeInTheDocument();
  });

  it('loads unlisted chapter detail on click', async () => {
    getUnlisted.mockResolvedValue({
      book_id: 'book-1',
      title: 'Unlisted A',
      summary_excerpt: 'summary',
      original_language: 'vi',
    });
    listUnlistedChapters.mockResolvedValue({
      items: [{ chapter_id: 'c1', title: 'Chapter 1', sort_order: 1, original_language: 'vi' }],
      total: 1,
    });
    getUnlistedChapter.mockResolvedValueOnce({
      chapter_id: 'c1',
      title: 'Chapter 1',
      sort_order: 1,
      original_language: 'vi',
      body: 'unlisted body',
    });

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Chapter 1/ }));

    await waitFor(() => expect(getUnlistedChapter).toHaveBeenCalledWith('token-abc', 'c1'));
    expect(await screen.findByText('unlisted body')).toBeInTheDocument();
  });
});
