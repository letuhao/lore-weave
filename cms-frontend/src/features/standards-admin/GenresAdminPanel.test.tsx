import { render, screen, fireEvent, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SystemGenre } from './types';

const createMutate = vi.fn();
const updateMutate = vi.fn();
const removeMutate = vi.fn();

const data: SystemGenre[] = [
  { genre_id: 'g1', code: 'fantasy', name: 'Fantasy', icon: '📖', color: '#7c3aed', sort_order: 1 },
  { genre_id: 'g2', code: 'scifi', name: 'Sci-Fi', icon: null, color: null, sort_order: 2 },
];

vi.mock('./hooks/useGenresAdmin', () => ({
  useGenresAdmin: () => ({
    list: { isLoading: false, isError: false, data },
    create: { isPending: false, mutate: createMutate },
    update: { isPending: false, mutate: updateMutate },
    remove: { isPending: false, mutate: removeMutate },
    status: null,
    clearStatus: () => {},
  }),
}));

import { GenresAdminPanel } from './GenresAdminPanel';

beforeEach(() => {
  createMutate.mockReset();
  updateMutate.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe('GenresAdminPanel', () => {
  it('filters rows by the search box (name/code, case-insensitive)', () => {
    render(<GenresAdminPanel />);
    expect(screen.getByText('Fantasy')).toBeInTheDocument();
    expect(screen.getByText('Sci-Fi')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'sci' } });
    expect(screen.queryByText('Fantasy')).toBeNull();
    expect(screen.getByText('Sci-Fi')).toBeInTheDocument();
  });

  it('emits color from the picker on create submit', () => {
    render(<GenresAdminPanel />);
    fireEvent.click(screen.getByRole('button', { name: /new genre/i }));

    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getAllByRole('textbox')[0], { target: { value: 'Horror' } });
    // the native color input
    fireEvent.change(screen.getByLabelText('Color picker'), { target: { value: '#112233' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(createMutate).toHaveBeenCalledTimes(1);
    expect(createMutate.mock.calls[0][0]).toMatchObject({ name: 'Horror', color: '#112233' });
  });
});
