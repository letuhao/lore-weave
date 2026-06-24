import { render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SystemTrash } from './types';

const restoreGenreMutate = vi.fn();
const restoreKindMutate = vi.fn();
const restoreAttributeMutate = vi.fn();

const trash: SystemTrash = {
  genres: [{ id: 'g1', code: 'cyberpunk', name: 'Cyberpunk', deprecated_at: '2026-06-20T00:00:00Z' }],
  kinds: [],
  attributes: [
    {
      id: 'a1',
      code: 'armor',
      name: 'Armor',
      kind_code: 'mecha',
      genre_code: 'cyberpunk',
      field_type: 'text',
      deprecated_at: '2026-06-20T00:00:00Z',
    },
  ],
};

vi.mock('./hooks/useRecycleBin', () => ({
  useRecycleBin: () => ({
    list: { isLoading: false, isError: false, data: trash },
    restoreGenre: { isPending: false, mutate: restoreGenreMutate },
    restoreKind: { isPending: false, mutate: restoreKindMutate },
    restoreAttribute: { isPending: false, mutate: restoreAttributeMutate },
    status: null,
    clearStatus: () => {},
  }),
}));

import { RecycleBinPanel } from './RecycleBinPanel';

afterEach(() => vi.clearAllMocks());

describe('RecycleBinPanel', () => {
  it('lists soft-deleted rows with the attribute cell context, and empty sections', () => {
    render(<RecycleBinPanel />);
    expect(screen.getByText('Cyberpunk')).toBeInTheDocument();
    expect(screen.getByText('Armor')).toBeInTheDocument();
    // attribute cell context: kind × genre / code · field_type
    expect(screen.getByText(/mecha × cyberpunk \/ armor · text/)).toBeInTheDocument();
    // the empty Kinds section
    expect(screen.getByText('Nothing here.')).toBeInTheDocument();
  });

  it('restores a genre and an attribute via the right mutation', () => {
    render(<RecycleBinPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Restore Cyberpunk' }));
    expect(restoreGenreMutate).toHaveBeenCalledWith('g1');

    fireEvent.click(screen.getByRole('button', { name: 'Restore Armor' }));
    expect(restoreAttributeMutate).toHaveBeenCalledWith('a1');
    expect(restoreKindMutate).not.toHaveBeenCalled();
  });
});
