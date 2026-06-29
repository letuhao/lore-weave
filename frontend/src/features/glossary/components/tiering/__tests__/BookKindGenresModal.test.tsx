import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { BookGenre } from '../../../tieringTypes';
import { BookKindGenresModal } from '../BookKindGenresModal';

function genre(id: string, code: string): BookGenre {
  return { genre_id: id, code, name: code, icon: '🐉', color: '#000', sort_order: 0, active: true };
}
const GENRES = [genre('g-fan', 'fantasy'), genre('g-xx', 'xianxia'), genre('g-rom', 'romance')];

describe('BookKindGenresModal', () => {
  it('seeds checkboxes from linkedGenreIds and saves the toggled replace-set, then closes', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <BookKindGenresModal
        kindName="Character"
        genres={GENRES}
        linkedGenreIds={['g-fan']}
        onSave={onSave}
        onClose={onClose}
      />,
    );

    const fantasy = screen.getByTestId('link-genre-fantasy') as HTMLInputElement;
    expect(fantasy.checked).toBe(true);
    expect((screen.getByTestId('link-genre-xianxia') as HTMLInputElement).checked).toBe(false);

    // Add xianxia, remove fantasy → the replace-set should be exactly [g-xx].
    fireEvent.click(screen.getByTestId('link-genre-xianxia'));
    fireEvent.click(fantasy);
    fireEvent.click(screen.getByTestId('book-links-save'));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const ids = onSave.mock.calls[0][0] as string[];
    expect([...ids].sort()).toEqual(['g-xx']);
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('disables Save when no genre is selected (book ≥1-genre invariant)', () => {
    const onSave = vi.fn();
    render(
      <BookKindGenresModal
        kindName="Character"
        genres={GENRES}
        linkedGenreIds={['g-fan']}
        onSave={onSave}
        onClose={vi.fn()}
      />,
    );

    const save = screen.getByTestId('book-links-save') as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    // Unlink the only genre → Save must lock so a kind can't be orphaned.
    fireEvent.click(screen.getByTestId('link-genre-fantasy'));
    expect(save.disabled).toBe(true);
    fireEvent.click(save);
    expect(onSave).not.toHaveBeenCalled();
  });

  it('renders the empty hint and no checkboxes when the book has no genres', () => {
    render(
      <BookKindGenresModal
        kindName="Character"
        genres={[]}
        linkedGenreIds={[]}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('link-genre-fantasy')).not.toBeInTheDocument();
    // Save is disabled with an empty linkable set too.
    expect((screen.getByTestId('book-links-save') as HTMLButtonElement).disabled).toBe(true);
  });
});
