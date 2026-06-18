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

  it('filters out non-matching titles', async () => {
    listBooksMock.mockResolvedValue(BOOKS);
    render(<BookPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listBooksMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'winds' } });
    // wait for the debounced filter to drop the non-match (both render pre-debounce)
    await waitFor(() => expect(screen.queryByText('The Silk Road Chronicles')).toBeNull());
    expect(screen.getByText('Winds of the Eastern Sea')).toBeInTheDocument();
  });
});
