import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// W4 (G2) — WorldPicker: search worlds by name, emit the world_id (UUID), empty
// selection stays valid, optional inline "create new", unlisted fallback.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test', user: { user_id: 'u1' } }),
}));

const listWorldsMock = vi.fn();
const getWorldMock = vi.fn();
vi.mock('@/features/world/api', () => ({
  worldsApi: {
    listWorlds: (...a: unknown[]) => listWorldsMock(...a),
    getWorld: (...a: unknown[]) => getWorldMock(...a),
  },
}));

import { WorldPicker } from '../WorldPicker';

const WORLDS = {
  items: [
    { world_id: 'w-aaaa', name: 'Aethyr Expanse', book_count: 3 },
    { world_id: 'w-bbbb', name: 'Verdant Reaches', book_count: 1 },
  ],
  total: 2,
};

describe('WorldPicker (W4)', () => {
  beforeEach(() => {
    listWorldsMock.mockReset();
    getWorldMock.mockReset();
  });

  it('searches by name and emits the world_id (not the name)', async () => {
    listWorldsMock.mockResolvedValue(WORLDS);
    const onChange = vi.fn();
    render(<WorldPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(listWorldsMock).toHaveBeenCalled());
    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'verdant' } });
    const option = await screen.findByText('Verdant Reaches');
    fireEvent.click(option);
    expect(onChange).toHaveBeenCalledWith('w-bbbb');
  });

  it('empty selection is valid — nothing emitted until a pick', async () => {
    listWorldsMock.mockResolvedValue(WORLDS);
    const onChange = vi.fn();
    render(<WorldPicker value={null} onChange={onChange} />);
    await waitFor(() => expect(listWorldsMock).toHaveBeenCalled());
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('shows the selected name and clears back to null', async () => {
    listWorldsMock.mockResolvedValue(WORLDS);
    const onChange = vi.fn();
    render(<WorldPicker value="w-aaaa" onChange={onChange} />);
    await waitFor(() => expect(listWorldsMock).toHaveBeenCalled());
    expect(await screen.findByTestId('world-picker-selected')).toHaveTextContent(
      'Aethyr Expanse',
    );
    fireEvent.click(screen.getByLabelText('Clear selected world'));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('filters out non-matching names', async () => {
    listWorldsMock.mockResolvedValue(WORLDS);
    render(<WorldPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listWorldsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'aethyr' } });
    await waitFor(() => expect(screen.queryByText('Verdant Reaches')).toBeNull());
    expect(screen.getByText('Aethyr Expanse')).toBeInTheDocument();
  });

  it('resolves a selected-but-unlisted world by id for the chip', async () => {
    listWorldsMock.mockResolvedValue(WORLDS);
    getWorldMock.mockResolvedValue({ world_id: 'w-cccc', name: 'Hidden Vale', book_count: 0 });
    render(<WorldPicker value="w-cccc" onChange={vi.fn()} />);
    await waitFor(() => expect(getWorldMock).toHaveBeenCalledWith('tok-test', 'w-cccc'));
    expect(await screen.findByTestId('world-picker-selected')).toHaveTextContent('Hidden Vale');
  });

  it('renders an inline "create new" row only when onCreateNew is given', async () => {
    listWorldsMock.mockResolvedValue(WORLDS);
    const onCreateNew = vi.fn();
    render(<WorldPicker value={null} onChange={vi.fn()} onCreateNew={onCreateNew} />);
    await waitFor(() => expect(listWorldsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    const create = await screen.findByText('Create new world');
    fireEvent.click(create);
    expect(onCreateNew).toHaveBeenCalledTimes(1);
  });
});
