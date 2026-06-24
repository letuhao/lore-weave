import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));

// Stub BookPicker to a simple control that emits a fixed id on click.
vi.mock('@/components/shared/BookPicker', () => ({
  BookPicker: ({ onChange }: { onChange: (id: string | null) => void }) => (
    <button type="button" data-testid="stub-book-pick" onClick={() => onChange('b-picked')}>
      pick
    </button>
  ),
}));

const attach = vi.fn();
const createAndAttach = vi.fn();
const hook = vi.fn();
vi.mock('../../hooks/useAddBookToWorld', () => ({
  useAddBookToWorld: () => hook(),
}));

import { AddBookToWorldModal } from '../AddBookToWorldModal';

beforeEach(() => {
  attach.mockReset();
  createAndAttach.mockReset();
  hook.mockReturnValue({ attach, createAndAttach, isPending: false, error: null });
});

function renderModal(onOpenChange = vi.fn()) {
  render(<AddBookToWorldModal open onOpenChange={onOpenChange} worldId="w1" />);
  return onOpenChange;
}

describe('AddBookToWorldModal (W5/G1)', () => {
  it('attaches a picked existing book and closes on success', async () => {
    attach.mockResolvedValue({ book_id: 'b-picked', world_id: 'w1' });
    const onOpenChange = renderModal();
    // submit is disabled until a book is picked.
    expect(screen.getByTestId('add-book-submit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('stub-book-pick'));
    fireEvent.click(screen.getByTestId('add-book-submit'));
    await waitFor(() => expect(attach).toHaveBeenCalledWith('b-picked'));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('creates a new book then attaches it from the create tab', async () => {
    createAndAttach.mockResolvedValue({ book_id: 'b-new' });
    renderModal();
    fireEvent.click(screen.getByTestId('add-book-mode-create'));
    // submit disabled until a title is typed.
    expect(screen.getByTestId('add-book-submit')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Brave New Book' } });
    fireEvent.click(screen.getByTestId('add-book-submit'));
    await waitFor(() =>
      expect(createAndAttach).toHaveBeenCalledWith({ title: 'Brave New Book', description: undefined }),
    );
  });

  it('keeps the modal open and shows the error when an add fails', async () => {
    hook.mockReturnValue({ attach, createAndAttach, isPending: false, error: new Error('boom') });
    const onOpenChange = renderModal();
    expect(screen.getByTestId('add-book-error')).toBeInTheDocument();
    // an error state didn't auto-close the modal.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
