// RAID C1 — useSteering controller: list query + create/update/delete mutations, cap flag, and
// the 409/422 → duplicate/cap error classification the editor renders.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import { useSteering, classifySteeringError } from '../useSteering';
import type { SteeringEntry } from '../../types';

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }) }));
vi.mock('../../api', () => ({ steeringApi: apiMocks }));

const entry = (over: Partial<SteeringEntry> = {}): SteeringEntry => ({
  id: 'e1', book_id: 'b1', name: 'Tone', body: 'Keep it terse.',
  inclusion_mode: 'always', match_pattern: null, enabled: true,
  author_user_id: 'u1', created_at: '', updated_at: '', ...over,
});

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: PropsWithChildren) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => vi.clearAllMocks());

describe('useSteering', () => {
  it('lists entries for the book', async () => {
    apiMocks.list.mockResolvedValue([entry()]);
    const { result } = renderHook(() => useSteering('b1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.entries).toHaveLength(1));
    expect(apiMocks.list).toHaveBeenCalledWith('tok', 'b1');
    expect(result.current.atCap).toBe(false);
  });

  it('does not query without a bookId', async () => {
    apiMocks.list.mockResolvedValue([]);
    renderHook(() => useSteering(null), { wrapper: wrapper() });
    await new Promise((r) => setTimeout(r, 0));
    expect(apiMocks.list).not.toHaveBeenCalled();
  });

  it('atCap once 20 rows exist', async () => {
    apiMocks.list.mockResolvedValue(Array.from({ length: 20 }, (_, i) => entry({ id: `e${i}` })));
    const { result } = renderHook(() => useSteering('b1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.entries).toHaveLength(20));
    expect(result.current.atCap).toBe(true);
  });

  it('create/update/delete call the api with the right args', async () => {
    apiMocks.list.mockResolvedValue([]);
    apiMocks.create.mockResolvedValue(entry());
    apiMocks.update.mockResolvedValue(entry());
    apiMocks.remove.mockResolvedValue(undefined);
    const { result } = renderHook(() => useSteering('b1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.createEntry({ name: 'A', body: 'x' }); });
    expect(apiMocks.create).toHaveBeenCalledWith('tok', 'b1', { name: 'A', body: 'x' });

    await act(async () => { await result.current.updateEntry('e1', { enabled: false }); });
    expect(apiMocks.update).toHaveBeenCalledWith('tok', 'b1', 'e1', { enabled: false });

    await act(async () => { await result.current.deleteEntry('e1'); });
    expect(apiMocks.remove).toHaveBeenCalledWith('tok', 'b1', 'e1');
  });

  it('surfaces a rejected create so the caller can classify it', async () => {
    apiMocks.list.mockResolvedValue([]);
    apiMocks.create.mockRejectedValue(Object.assign(new Error('dup'), { status: 409 }));
    const { result } = renderHook(() => useSteering('b1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    let caught: unknown;
    await act(async () => { await result.current.createEntry({ name: 'A', body: 'x' }).catch((e) => { caught = e; }); });
    expect(classifySteeringError(caught)).toBe('duplicate');
  });
});

describe('classifySteeringError', () => {
  it.each([
    [409, 'duplicate'],
    [422, 'cap'],
    [500, 'other'],
  ] as const)('%s → %s', (status, kind) => {
    expect(classifySteeringError(Object.assign(new Error('x'), { status }))).toBe(kind);
  });
  it('null for no error', () => expect(classifySteeringError(null)).toBe(null));
});
