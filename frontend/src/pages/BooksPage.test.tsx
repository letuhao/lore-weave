import { describe, expect, it, vi, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { BooksPage } from './BooksPage';

const listBooks = vi.fn();
const createBook = vi.fn();

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'token-1' }),
}));

vi.mock('@/m02/api', () => ({
  m02Api: {
    listBooks: (...args: unknown[]) => listBooks(...args),
    createBook: (...args: unknown[]) => createBook(...args),
  },
}));

describe('BooksPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  it('loads and renders books list', async () => {
    listBooks.mockResolvedValueOnce({
      items: [
        {
          book_id: 'b1',
          owner_user_id: 'u1',
          title: 'Book One',
          chapter_count: 2,
          lifecycle_state: 'active',
          original_language: 'en',
        },
      ],
      total: 1,
    });

    render(
      <MemoryRouter>
        <BooksPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Book One')).toBeInTheDocument();
    expect(listBooks).toHaveBeenCalledWith('token-1');
  });

  it('creates a book and reloads list', async () => {
    listBooks.mockResolvedValue({ items: [], total: 0 });
    createBook.mockResolvedValue({
      book_id: 'b2',
      owner_user_id: 'u1',
      title: 'New Book',
      chapter_count: 0,
      lifecycle_state: 'active',
    });

    render(
      <MemoryRouter>
        <BooksPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText('Title'), {
      target: { value: 'New Book' },
    });
    fireEvent.change(screen.getByPlaceholderText('Original language (e.g. en)'), {
      target: { value: 'vi' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(createBook).toHaveBeenCalledWith('token-1', {
        title: 'New Book',
        original_language: 'vi',
      }),
    );
    expect(listBooks).toHaveBeenCalledTimes(2);
  });
});
