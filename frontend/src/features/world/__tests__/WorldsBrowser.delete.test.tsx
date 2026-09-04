import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// P3 — `world_delete` was the worst gap the parity census found, by a distance.
//
// 🔴 MEASURED over the live chat store, 2026-09-04:
//
//     world_delete   92 calls   92 failed   (100%)
//
// Every one refused for the same reason — the model called it with no `world_id`. And the census
// verdict for it was `NONE`: **there was no way to delete a world in the UI either.** A capability
// the agent attempts constantly, never once completes, and the user cannot do by hand is exactly
// the owner's "ship feature that user cannot use and agent is dumb".
//
// 🔴 THE GUARD IS THE HARD PART, AND IT IS NOT THE BUTTON'S `disabled` PROP.
// `books.world_id` is `ON DELETE SET NULL`, so `DELETE /v1/worlds/{id}` SILENTLY ORPHANS member
// books. The MCP tool carries a guard the naked REST route lacks — it refuses while the world
// still holds books — sealed as **D-S07-world-delete-guard**. A UI that called the route without
// that check would re-open the precise footgun the tool was hardened against, because *replacing
// a surface does not inherit its guarantees*. So the refusal lives in the mutation, and the
// disabled button is only the hint.

// t() must resolve to the SHIPPED English string, not the key, or the title assertion below
// would pass against 'card.delete_blocked' and prove nothing about what a user reads.
vi.mock('react-i18next', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useTranslation: () => ({
    t: (k: string, o?: { defaultValue?: string; count?: number; name?: string }) =>
      (o?.defaultValue ?? k)
        .replace('{{count}}', String(o?.count ?? ''))
        .replace('{{name}}', String(o?.name ?? '')),
    i18n: { language: 'en', changeLanguage: () => Promise.resolve() },
  }),
}));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-1' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

const { deleteWorld, listWorlds, createWorld } = vi.hoisted(() => ({
  deleteWorld: vi.fn(() => Promise.resolve()),
  listWorlds: vi.fn(),
  createWorld: vi.fn(),
}));
vi.mock('../api', () => ({ worldsApi: { deleteWorld, listWorlds, createWorld } }));

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WorldsBrowser } from '../components/WorldsBrowser';

const world = (over: Partial<Record<string, unknown>> = {}) => ({
  world_id: 'w1', name: 'Vurn', description: '', owner_user_id: 'u1',
  bible_book_id: null, bible_chapter_id: null, created_at: '', updated_at: '',
  book_count: 0, ...over,
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><WorldsBrowser /></QueryClientProvider>,
  );
}

beforeEach(() => {
  deleteWorld.mockClear();
  deleteWorld.mockResolvedValue(undefined);
});

describe('WorldsBrowser — the manual path for world_delete', () => {
  it('offers a delete control on an empty world', async () => {
    listWorlds.mockResolvedValue({ items: [world()], total: 1 });
    mount();
    const btn = await screen.findByTestId('world-delete-w1');
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it('🔴 D-S07: the control is DISABLED while the world holds books', async () => {
    // The orphaning case. `book_count > 0` means a delete would detach these books rather than
    // delete them, which is why the MCP tool refuses outright.
    listWorlds.mockResolvedValue({ items: [world({ book_count: 3 })], total: 1 });
    mount();
    const btn = await screen.findByTestId('world-delete-w1');
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    expect(btn.getAttribute('title')).toMatch(/move its/i);
  });

  it('🔴 D-S07: and the MUTATION refuses too, not just the button', async () => {
    // The arm that matters. A `disabled` prop is a hint — it is bypassed by a stale render, a
    // keyboard path, or any future caller of the hook. The guard has to live where the write is.
    const { useWorlds } = await import('../hooks/useWorlds');
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    let hook: ReturnType<typeof useWorlds> | undefined;
    function Probe() { hook = useWorlds(); return null; }
    render(<QueryClientProvider client={qc}><Probe /></QueryClientProvider>);
    await waitFor(() => expect(hook).toBeTruthy());

    await expect(
      hook!.deleteWorld(world({ book_count: 2 }) as never),
    ).rejects.toThrow(/still holds 2 book/i);
    expect(deleteWorld, 'the API must never be reached for a populated world').not.toHaveBeenCalled();
  });

  it('deleting is a two-step — one click does not destroy anything', async () => {
    // Irreversible: the world's lore, maps and timeline go with it. A single mis-click must not
    // be enough.
    listWorlds.mockResolvedValue({ items: [world()], total: 1 });
    mount();
    fireEvent.click(await screen.findByTestId('world-delete-w1'));
    expect(deleteWorld).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByTestId('world-delete-confirm'));
    await waitFor(() => expect(deleteWorld).toHaveBeenCalledWith('tok-1', 'w1'));
  });
});
