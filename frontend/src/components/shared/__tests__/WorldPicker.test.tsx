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

  // ── the name filter is the SERVER'S ──────────────────────────────────────
  //
  // This used to mock `listWorlds` to return every world whatever was asked for
  // and assert that typing hid the non-matches — which only passes while the
  // filtering happens in the browser, and the browser only ever held one
  // clamped page. `q` was added to `GET /v1/worlds` for this; the mock now
  // behaves like the endpoint, and the assertions pin the REQUEST as well as
  // the render so a re-added client-side `.filter()` cannot pass.
  const serverSideList = (_t: string, params?: { q?: string }) => {
    const q = (params?.q ?? '').toLowerCase();
    const items = q
      ? WORLDS.items.filter((w) => w.name.toLowerCase().includes(q))
      : WORLDS.items;
    return Promise.resolve({ items, total: items.length });
  };

  it('sends the typed name to the server rather than filtering in the browser', async () => {
    listWorldsMock.mockImplementation(serverSideList);
    render(<WorldPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listWorldsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'aethyr' } });

    await waitFor(() =>
      expect(listWorldsMock).toHaveBeenCalledWith(
        'tok-test',
        expect.objectContaining({ q: 'aethyr' }),
      ),
    );
    await waitFor(() => expect(screen.queryByText('Verdant Reaches')).toBeNull());
    expect(screen.getByText('Aethyr Expanse')).toBeInTheDocument();
  });

  it('renders what the server returned even when it does not contain the typed text', async () => {
    // THE DISCRIMINATING CASE — a client-side `includes()` would hide this row.
    // The server decides what matches, and it can do what the browser cannot.
    listWorldsMock.mockResolvedValue({
      items: [{ world_id: 'w-cccc', name: 'Verdant Reaches', book_count: 1 }],
      total: 1,
    });
    render(<WorldPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listWorldsMock).toHaveBeenCalled());
    fireEvent.focus(screen.getByRole('combobox'));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'aethyr' } });
    // Wait PAST the 180ms debounce — see ProjectPicker: asserting immediately
    // races it and the test agrees with a re-added client-side filter.
    await new Promise((r) => setTimeout(r, 320));
    expect(screen.getByText('Verdant Reaches')).toBeInTheDocument();
  });

  it('an empty box asks for no q at all, rather than searching for ""', async () => {
    listWorldsMock.mockImplementation(serverSideList);
    render(<WorldPicker value={null} onChange={vi.fn()} />);
    await waitFor(() => expect(listWorldsMock).toHaveBeenCalled());
    expect(listWorldsMock.mock.calls[0][1]).not.toHaveProperty('q');
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
