import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// C4 (BL-3) — BookPicker: search books by title, emit the book_id (UUID), empty
// selection stays valid.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test', user: { user_id: 'u1' } }),
}));

const listBooksMock = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { listBooks: (...a: unknown[]) => listBooksMock(...a) },
}));

import { BookPicker } from '../BookPicker';

const BOOKS = {
  items: [
    { book_id: 'b-aaaa', title: 'Winds of the Eastern Sea', chapter_count: 45 },
    { book_id: 'b-bbbb', title: 'The Silk Road Chronicles', chapter_count: 230 },
  ],
  total: 2,
};

// The mock APPLIES ?q, because the title filter now lives on the server. A mock
// that returns the same rows whatever it is asked cannot tell a picker that
// searched from one that did not — and the picker previously filtered in the
// browser over a list the endpoint had already truncated to 100 (it asks for
// 200; parseLimitOffset clamps). At 83 books that is invisible; at 101 the
// picker starts omitting books silently.
function respondToQuery(...a: unknown[]) {
  const q = String((a[1] as { q?: string } | undefined)?.q ?? '').toLowerCase();
  const items = q ? BOOKS.items.filter((b) => b.title.toLowerCase().includes(q)) : BOOKS.items;
  return Promise.resolve({ items, total: items.length });
}

describe('BookPicker (C4)', () => {
  beforeEach(() => listBooksMock.mockReset());

  it('searches by title and emits the book_id (not the title)', async () => {
    listBooksMock.mockResolvedValue(BOOKS);
    const onChange = vi.fn();
    render(<BookPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(listBooksMock).toHaveBeenCalled());
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'silk' } });
    const option = await screen.findByText('The Silk Road Chronicles');
    fireEvent.click(option);
    // emits the UUID, never the title
    expect(onChange).toHaveBeenCalledWith('b-bbbb');
  });

  it('empty selection is valid — nothing emitted until a pick', async () => {
    listBooksMock.mockResolvedValue(BOOKS);
    const onChange = vi.fn();
    render(<BookPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(listBooksMock).toHaveBeenCalled());
    // no interaction → no emit; the picker renders as a searchable combobox
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('shows the selected title and clears back to null', async () => {
    listBooksMock.mockResolvedValue(BOOKS);
    const onChange = vi.fn();
    render(<BookPicker value="b-aaaa" onChange={onChange} />);
    await waitFor(() => expect(listBooksMock).toHaveBeenCalled());
    expect(await screen.findByTestId('book-picker-selected')).toHaveTextContent(
      'Winds of the Eastern Sea',
    );
    fireEvent.click(screen.getByLabelText('Clear selected book'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('sends the title filter to the SERVER as ?q, and renders what comes back', async () => {
    listBooksMock.mockImplementation(respondToQuery);
    render(<BookPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listBooksMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'winds' } });

    // The REQUEST is the assertion that matters: a filter that never leaves the
    // browser is the defect, and a rendered list alone cannot distinguish them.
    await waitFor(() =>
      expect(listBooksMock).toHaveBeenCalledWith(
        'tok-test',
        expect.objectContaining({ q: 'winds' }),
      ),
    );
    await waitFor(() => expect(screen.queryByText('The Silk Road Chronicles')).toBeNull());
    expect(screen.getByText('Winds of the Eastern Sea')).toBeInTheDocument();
  });

  it("keeps the selected book's title after a search that excludes it", async () => {
    // The label used to be re-derived from the loaded page. Once the page is a
    // search result the chosen book is usually absent from it, so deriving would
    // blank the picker's own label the moment you typed.
    listBooksMock.mockImplementation(respondToQuery);
    const { rerender } = render(<BookPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listBooksMock).toHaveBeenCalled());
    rerender(<BookPicker value="b-bbbb" onChange={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId('book-picker-selected')).toHaveTextContent(
        'The Silk Road Chronicles',
      ),
    );
  });

  it('says how many matches it is NOT showing', async () => {
    // A picker that quietly lists 100 of 140 is indistinguishable from one whose
    // user has 100 books. The count has to be on screen.
    listBooksMock.mockResolvedValue({ items: BOOKS.items, total: 140 });
    render(<BookPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listBooksMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    expect(await screen.findByTestId('book-picker-truncated')).toHaveTextContent('138 more');
  });
});
