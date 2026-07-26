import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { BookGenre, BookKind, BookOntology } from '../../../tieringTypes';

// Hook controllers are mocked so the test exercises ManageWorkspace's wiring
// (auto-link-on-create + the links action) without a network/QueryClient.
const ont = vi.hoisted(() => ({ value: null as unknown }));
vi.mock('@/features/glossary/hooks/useBookOntology', () => ({
  useBookOntology: () => ont.value,
}));
vi.mock('@/features/glossary/hooks/useStandards', () => ({
  useStandards: () => ({ genres: [], kinds: [], isLoading: false, error: null }),
}));

import { ManageWorkspace } from '../ManageWorkspace';

function genre(id: string, code: string): BookGenre {
  return { genre_id: id, code, name: code, icon: '🐉', color: '#000', sort_order: 0, active: true, source_ref: null };
}
function kind(id: string, name: string): BookKind {
  return { book_kind_id: id, code: id, name, icon: 'box', color: '#000', sort_order: 0, is_hidden: false, source_ref: null };
}

function makeOnt(ontology: BookOntology, spies: Partial<Record<string, ReturnType<typeof vi.fn>>> = {}) {
  const noop = () => vi.fn().mockResolvedValue(undefined);
  return {
    ontology,
    isAdopted: ontology.kinds.length >= 0,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    adopt: noop(),
    createGenre: spies.createGenre ?? noop(),
    patchGenre: noop(),
    deleteGenre: noop(),
    createKind: spies.createKind ?? noop(),
    patchKind: noop(),
    deleteKind: noop(),
    setKindGenres: spies.setKindGenres ?? noop(),
    createAttribute: noop(),
    patchAttribute: noop(),
    deleteAttribute: noop(),
    revertGenre: noop(),
    revertKind: noop(),
    revertAttribute: noop(),
    setActiveGenres: noop(),
  };
}

beforeEach(() => {
  ont.value = null;
});

describe('ManageWorkspace #25 wiring', () => {
  it('auto-links a newly created book kind to the genre it was created under', async () => {
    const createKind = vi.fn().mockResolvedValue({ book_kind_id: 'k-new' });
    const setKindGenres = vi.fn().mockResolvedValue([]);
    ont.value = makeOnt(
      { book_id: 'b1', genres: [genre('g1', 'fantasy')], kinds: [], kind_genres: [], attributes: [] },
      { createKind, setKindGenres },
    );

    render(<ManageWorkspace bookId="b1" />);

    // Pick the genre, then open the kinds column's "new kind" quick-create.
    fireEvent.click(screen.getByTestId('ontology-row-g1'));
    fireEvent.click(screen.getByText('col.new_kind'));
    fireEvent.change(screen.getByPlaceholderText('quickcreate.name_placeholder'), { target: { value: 'Sect' } });
    fireEvent.click(screen.getByText('quickcreate.create'));

    // The kind is created, THEN linked to the selected genre — without the link it
    // would be invisible in this genre-first drilldown (the create-then-vanish bug).
    await waitFor(() => expect(createKind).toHaveBeenCalled());
    await waitFor(() => expect(setKindGenres).toHaveBeenCalledWith('k-new', ['g1']));
  });

  it('opens the book kind↔genre editor from a kind row links action', () => {
    ont.value = makeOnt({
      book_id: 'b1',
      genres: [genre('g1', 'fantasy')],
      kinds: [kind('k1', 'Character')],
      kind_genres: [{ kind_id: 'k1', genre_id: 'g1' }],
      attributes: [],
    });

    render(<ManageWorkspace bookId="b1" />);
    fireEvent.click(screen.getByTestId('ontology-row-g1'));
    // The kind is linked to g1, so it appears in the kinds column with a links action.
    fireEvent.click(screen.getByTestId('ontology-links-k1'));
    expect(screen.getByTestId('book-kind-genres-modal')).toBeInTheDocument();
    // Its current link (fantasy) is seeded as checked.
    expect((screen.getByTestId('link-genre-fantasy') as HTMLInputElement).checked).toBe(true);
  });
});
