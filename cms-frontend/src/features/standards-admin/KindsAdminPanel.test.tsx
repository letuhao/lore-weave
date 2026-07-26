import { render, screen, fireEvent, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SystemKind } from './types';

const createMutate = vi.fn();
const updateMutate = vi.fn();
const removeMutate = vi.fn();

const data: SystemKind[] = [
  { kind_id: 'k1', code: 'character', name: 'Character', description: null, icon: '👤', color: '#7c3aed', is_hidden: false, sort_order: 1 },
  { kind_id: 'k2', code: 'location', name: 'Location', description: null, icon: null, color: null, is_hidden: false, sort_order: 2 },
];

vi.mock('./hooks/useKindsAdmin', () => ({
  useKindsAdmin: () => ({
    list: { isLoading: false, isError: false, data },
    create: { isPending: false, mutate: createMutate },
    update: { isPending: false, mutate: updateMutate },
    remove: { isPending: false, mutate: removeMutate },
    status: null,
    clearStatus: () => {},
  }),
}));

import { KindsAdminPanel } from './KindsAdminPanel';

beforeEach(() => {
  createMutate.mockReset();
  updateMutate.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe('KindsAdminPanel', () => {
  it('filters rows by the search box', () => {
    render(<KindsAdminPanel />);
    expect(screen.getByText('Character')).toBeInTheDocument();
    expect(screen.getByText('Location')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'loc' } });
    expect(screen.queryByText('Character')).toBeNull();
    expect(screen.getByText('Location')).toBeInTheDocument();
  });

  it('emits color from the picker on create submit', () => {
    render(<KindsAdminPanel />);
    fireEvent.click(screen.getByRole('button', { name: /new kind/i }));

    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getAllByRole('textbox')[0], { target: { value: 'Faction' } });
    fireEvent.change(screen.getByLabelText('Color picker'), { target: { value: '#445566' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(createMutate).toHaveBeenCalledTimes(1);
    expect(createMutate.mock.calls[0][0]).toMatchObject({ name: 'Faction', color: '#445566' });
  });
});
