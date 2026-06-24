import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const tiering = vi.hoisted(() => ({
  listGenres: vi.fn(),
  listUserKinds: vi.fn(),
  createUserGenre: vi.fn(),
  createUserKind: vi.fn(),
}));
vi.mock('@/features/glossary/tieringApi', () => ({ tieringApi: tiering }));

const glossary = vi.hoisted(() => ({ getKinds: vi.fn() }));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: glossary }));

import { useUserStandards } from '../useUserStandards';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  Object.values(tiering).forEach((m) => m.mockReset());
  glossary.getKinds.mockReset();
  // fantasy in BOTH tiers (user shadows), xianxia user-only, romance system-only.
  tiering.listGenres.mockResolvedValue([
    { genre_id: 'sys-fan', tier: 'system', code: 'fantasy', name: 'Fantasy', icon: '🐉', color: '#000', sort_order: 1 },
    { genre_id: 'usr-fan', tier: 'user', code: 'fantasy', name: 'Fantasy (mine)', icon: '🐉', color: '#000', sort_order: 1, cloned_from_genre_id: 'sys-fan' },
    { genre_id: 'usr-xx', tier: 'user', code: 'xianxia', name: 'Xianxia', icon: '⚔️', color: '#000', sort_order: 2 },
    { genre_id: 'sys-rom', tier: 'system', code: 'romance', name: 'Romance', icon: '💕', color: '#000', sort_order: 3 },
  ]);
  glossary.getKinds.mockResolvedValue([
    { kind_id: 'sys-char', code: 'character', name: 'Character', icon: '👤', color: '#000', description: 'a person' },
    { kind_id: 'sys-loc', code: 'location', name: 'Location', icon: '📍', color: '#000' },
  ]);
  tiering.listUserKinds.mockResolvedValue([
    { user_kind_id: 'usr-char', code: 'character', name: 'Character (mine)', icon: '👤', color: '#000', is_active: true, cloned_from_kind_id: 'sys-char' },
  ]);
  tiering.createUserGenre.mockResolvedValue({});
  tiering.createUserKind.mockResolvedValue({});
});

describe('useUserStandards', () => {
  it('merges genres by code with the User row shadowing System', async () => {
    const { result } = renderHook(() => useUserStandards(), { wrapper });
    await waitFor(() => expect(result.current.genres.length).toBe(3));
    const fantasy = result.current.genres.find((g) => g.code === 'fantasy')!;
    expect(fantasy.tier).toBe('user'); // user shadows system
    expect(fantasy.genre_id).toBe('usr-fan');
    expect(result.current.genres.find((g) => g.code === 'romance')!.tier).toBe('system');
    expect(result.current.genres.find((g) => g.code === 'xianxia')!.tier).toBe('user');
  });

  it('merges kinds by code with the User row shadowing System', async () => {
    const { result } = renderHook(() => useUserStandards(), { wrapper });
    await waitFor(() => expect(result.current.kinds.length).toBe(2));
    const character = result.current.kinds.find((k) => k.code === 'character')!;
    expect(character.tier).toBe('user');
    expect(character.id).toBe('usr-char');
    expect(result.current.kinds.find((k) => k.code === 'location')!.tier).toBe('system');
  });

  it('clones a System genre with clone_from_genre_id set to the system id', async () => {
    const { result } = renderHook(() => useUserStandards(), { wrapper });
    await waitFor(() => expect(result.current.genres.length).toBe(3));
    const romance = result.current.genres.find((g) => g.code === 'romance')!;
    await act(async () => { await result.current.cloneGenre.mutateAsync(romance); });
    expect(tiering.createUserGenre).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'romance', clone_from_genre_id: 'sys-rom' }),
      'tok',
    );
  });

  it('clones a System kind with clone_from_kind_id set to the system id', async () => {
    const { result } = renderHook(() => useUserStandards(), { wrapper });
    await waitFor(() => expect(result.current.kinds.length).toBe(2));
    const location = result.current.kinds.find((k) => k.code === 'location')!;
    await act(async () => { await result.current.cloneKind.mutateAsync(location); });
    expect(tiering.createUserKind).toHaveBeenCalledWith(
      expect.objectContaining({ code: 'location', clone_from_kind_id: 'sys-loc' }),
      'tok',
    );
  });
});
