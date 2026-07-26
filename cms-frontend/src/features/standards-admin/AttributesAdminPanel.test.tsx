import { render, screen, fireEvent, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SystemAttribute } from './types';

// Hook mocks — the panel is a pure view over these controllers.
const createMutate = vi.fn();
const updateMutate = vi.fn();
const removeMutate = vi.fn();

const kinds = [{ kind_id: 'k1', code: 'character', name: 'Character', description: null, icon: null, color: null, is_hidden: false, sort_order: 1 }];
const genres = [{ genre_id: 'g1', code: 'fantasy', name: 'Fantasy', icon: null, color: null, sort_order: 1 }];

let attrRows: SystemAttribute[] = [];

vi.mock('./hooks/useAttributesAdmin', () => ({
  useAttributesAdmin: (kindId: string, genreId: string) => ({
    kinds: { data: kinds },
    genres: { data: genres },
    attributes: { isLoading: false, isError: false, data: attrRows },
    selected: Boolean(kindId && genreId),
    create: { isPending: false, mutate: createMutate },
    update: { isPending: false, mutate: updateMutate },
    remove: { isPending: false, mutate: removeMutate },
    status: null,
    clearStatus: () => {},
  }),
}));

vi.mock('./hooks/useAttributeMatrix', () => ({
  useAttributeMatrix: () => ({
    activeGenres: genres,
    attributes: [],
    isLoading: false,
    isError: false,
    genres: { isSuccess: true },
  }),
}));

import { AttributesAdminPanel } from './AttributesAdminPanel';

function rank(over: Partial<SystemAttribute> = {}): SystemAttribute {
  return {
    attr_id: 'a1', kind_id: 'k1', genre_id: 'g1', code: 'rank', name: 'Rank',
    description: null, field_type: 'text', is_required: false, sort_order: 1, options: null,
    ...over,
  };
}

// Choose a kind + genre so `selected` is true and the table renders.
function selectKindGenre() {
  fireEvent.change(screen.getByDisplayValue('Select a kind…'), { target: { value: 'k1' } });
  fireEvent.change(screen.getByDisplayValue('Select a genre…'), { target: { value: 'g1' } });
}

beforeEach(() => {
  attrRows = [rank()];
  createMutate.mockReset();
  updateMutate.mockReset();
  removeMutate.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe('AttributesAdminPanel', () => {
  it('renders a field-type badge in the Type column', () => {
    attrRows = [rank({ field_type: 'select', options: ['a'] })];
    render(<AttributesAdminPanel />);
    selectKindGenre();
    const row = screen.getByText('Rank').closest('tr')!;
    expect(within(row).getByText('select')).toBeInTheDocument();
  });

  it('toggles between List and Matrix views', () => {
    render(<AttributesAdminPanel />);
    selectKindGenre();
    // list view shows the table row
    expect(screen.getByText('Rank')).toBeInTheDocument();
    // switch to Matrix → the cross-genre grid renders (genre column header), list table gone
    fireEvent.click(screen.getByRole('button', { name: 'Matrix' }));
    expect(screen.getByRole('columnheader', { name: 'Fantasy' })).toBeInTheDocument();
    expect(screen.queryByText('Rank')).toBeNull();
    // back to List
    fireEvent.click(screen.getByRole('button', { name: 'List' }));
    expect(screen.getByText('Rank')).toBeInTheDocument();
  });

  it('hides the Options textarea unless field_type is select or tags', () => {
    render(<AttributesAdminPanel />);
    selectKindGenre();
    fireEvent.click(screen.getByRole('button', { name: /new attribute/i }));

    // default field_type = text → no options textarea
    expect(screen.queryByText('Options (one per line)')).toBeNull();

    const typeSelect = screen.getByDisplayValue('text');
    fireEvent.change(typeSelect, { target: { value: 'select' } });
    expect(screen.getByText('Options (one per line)')).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue('select'), { target: { value: 'tags' } });
    expect(screen.getByText('Options (one per line)')).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue('tags'), { target: { value: 'number' } });
    expect(screen.queryByText('Options (one per line)')).toBeNull();
  });

  it('omits options on submit for a non-option field type', () => {
    render(<AttributesAdminPanel />);
    selectKindGenre();
    fireEvent.click(screen.getByRole('button', { name: /new attribute/i }));

    const dialog = screen.getByRole('dialog');
    const nameInput = within(dialog).getAllByRole('textbox')[0];
    fireEvent.change(nameInput, { target: { value: 'Height' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(createMutate).toHaveBeenCalledTimes(1);
    const body = createMutate.mock.calls[0][0];
    expect(body.options).toBeUndefined();
    expect(body.name).toBe('Height');
  });

  it('sends options for a select field type and blocks an empty select', () => {
    render(<AttributesAdminPanel />);
    selectKindGenre();
    fireEvent.click(screen.getByRole('button', { name: /new attribute/i }));

    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getAllByRole('textbox')[0], { target: { value: 'Role' } });
    fireEvent.change(screen.getByDisplayValue('text'), { target: { value: 'select' } });

    // empty options → submit is blocked
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(createMutate).not.toHaveBeenCalled();

    // fill options → submit goes through with the parsed array
    fireEvent.change(screen.getByPlaceholderText(/option-a/), {
      target: { value: 'hero\nvillain' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(createMutate).toHaveBeenCalledTimes(1);
    expect(createMutate.mock.calls[0][0].options).toEqual(['hero', 'villain']);
  });
});
