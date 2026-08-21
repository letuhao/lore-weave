import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import '@/i18n';

// D-BOOKS-CREATE-TO-STUDIO — creating a book from /books should land the user
// straight in its Studio instead of back on the list waiting for a second
// click on the newly-created row.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const createBookMock = vi.fn();
const startNewFB2ImportMock = vi.fn();
const getImportJobMock = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: {
    listBooks: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    createBook: (...a: unknown[]) => createBookMock(...a),
    startNewFB2Import: (...a: unknown[]) => startNewFB2ImportMock(...a),
    getImportJob: (...a: unknown[]) => getImportJobMock(...a),
  },
}));
vi.mock('@/features/translation/api', () => ({
  translationApi: { getBookCoverage: vi.fn().mockResolvedValue({ known_languages: [] }) },
}));

import { BooksPage } from '../BooksPage';

function renderBooksPage() {
  return render(
    <MemoryRouter initialEntries={['/books']}>
      <Routes>
        <Route path="/books" element={<BooksPage />} />
        <Route path="/books/:bookId/studio" element={<div data-testid="studio-landed" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('BooksPage create-book navigation (D-BOOKS-CREATE-TO-STUDIO)', () => {
  beforeEach(() => {
    createBookMock.mockReset();
    startNewFB2ImportMock.mockReset();
    getImportJobMock.mockReset();
  });

  it('navigates straight into the Studio for the newly created book', async () => {
    createBookMock.mockResolvedValue({ book_id: 'new-book-1', title: 'New Book' });
    renderBooksPage();
    await waitFor(() => expect(screen.getByTestId('book-create-button')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('book-create-button'));
    fireEvent.change(screen.getByTestId('book-title-input'), { target: { value: 'New Book' } });
    fireEvent.change(screen.getByTestId('book-language-input'), { target: { value: 'en' } });
    fireEvent.click(screen.getByTestId('book-create-submit'));

    await waitFor(() => expect(screen.getByTestId('studio-landed')).toBeInTheDocument());
  });

  it('stays on /books when creation fails (no navigation)', async () => {
    createBookMock.mockRejectedValue(new Error('nope'));
    renderBooksPage();
    await waitFor(() => expect(screen.getByTestId('book-create-button')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('book-create-button'));
    fireEvent.change(screen.getByTestId('book-title-input'), { target: { value: 'Bad Book' } });
    fireEvent.change(screen.getByTestId('book-language-input'), { target: { value: 'en' } });
    fireEvent.click(screen.getByTestId('book-create-submit'));

    await waitFor(() => expect(createBookMock).toHaveBeenCalled());
    expect(screen.queryByTestId('studio-landed')).not.toBeInTheDocument();
    expect(screen.getByTestId('book-create-button')).toBeInTheDocument();
  });

  it('starts a new-book FB2 import from the primary /books dialog', async () => {
    const file = new File(['<FictionBook/>'], 'sample.fb2', { type: 'application/x-fictionbook+xml' });
    startNewFB2ImportMock.mockResolvedValue({ id: 'job-1', book_id: 'fb2-book-1', status: 'pending', chapters_created: 0 });
    getImportJobMock.mockResolvedValue({ id: 'job-1', book_id: 'fb2-book-1', status: 'processing', chapters_created: 0 });
    renderBooksPage();
    await waitFor(() => expect(screen.getByTestId('book-create-button')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('book-create-button'));
    fireEvent.change(screen.getByTestId('book-fb2-import-input'), { target: { files: [file] } });
    fireEvent.click(screen.getByTestId('book-create-submit'));

    await waitFor(() => expect(startNewFB2ImportMock).toHaveBeenCalledWith('tok', file, undefined, expect.any(Function)));
    expect(await screen.findByText('Processing FB2… 0 chapters created so far')).toBeInTheDocument();
    expect(screen.queryByTestId('studio-landed')).not.toBeInTheDocument();
  });
});
