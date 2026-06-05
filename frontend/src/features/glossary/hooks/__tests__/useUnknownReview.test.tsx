import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { UnknownEntity } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const apiMocks = vi.hoisted(() => ({
  listUnknownEntities: vi.fn(),
  reassignEntityKind: vi.fn(),
  createKindAlias: vi.fn(),
  createKind: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: apiMocks }));

import { useUnknownReview } from '../useUnknownReview';

const BOOK = 'book-1';
const E1: UnknownEntity = { entity_id: 'e1', name: '哪吒', source_kind_code: 'faction', status: 'draft', created_at: '2026-06-04T00:00:00Z' };
const E2: UnknownEntity = { entity_id: 'e2', name: '楊戩', source_kind_code: 'faction', status: 'draft', created_at: '2026-06-04T00:00:00Z' };
const E_NOCODE: UnknownEntity = { entity_id: 'e3', name: '番天印', source_kind_code: null, status: 'draft', created_at: '2026-06-04T00:00:00Z' };

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

async function mountHook(items: UnknownEntity[]) {
  apiMocks.listUnknownEntities.mockResolvedValue({ items, total: items.length });
  const { Wrapper, invalidateSpy } = makeWrapper();
  const { result } = renderHook(() => useUnknownReview(BOOK), { wrapper: Wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  return { result, invalidateSpy };
}

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
  apiMocks.reassignEntityKind.mockResolvedValue({ entity_id: 'x', kind_id: 'k' });
  apiMocks.createKindAlias.mockResolvedValue({ alias_id: 'a1', alias_code: 'faction', kind_id: 'k9', reassigned: 2 });
  apiMocks.createKind.mockResolvedValue({ kind_id: 'k-new', code: 'faction', name: 'Faction' });
});

describe('useUnknownReview', () => {
  it('loads the unknown queue for the book', async () => {
    const { result } = await mountHook([E1]);
    expect(apiMocks.listUnknownEntities).toHaveBeenCalledWith(BOOK, 'tok');
    expect(result.current.items).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('resolve existing + single reassigns just the entity and invalidates', async () => {
    const { result, invalidateSpy } = await mountHook([E1, E2]);
    let outcome;
    await act(async () => { outcome = await result.current.resolve(E1, { strategy: 'existing', kindId: 'k9', applyAll: false }); });
    expect(apiMocks.reassignEntityKind).toHaveBeenCalledWith(BOOK, 'e1', 'k9', 'tok');
    expect(apiMocks.createKindAlias).not.toHaveBeenCalled();
    expect(outcome).toEqual({ action: 'reassigned', name: '哪吒' });
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['glossary-unknown', BOOK]);
    expect(keys).toContainEqual(['glossary-entities', BOOK]);
    expect(keys).toContainEqual(['glossary-kinds']);
  });

  it('resolve existing + applyAll creates a reassigning alias scoped to the book', async () => {
    const { result } = await mountHook([E1, E2]);
    let outcome;
    await act(async () => { outcome = await result.current.resolve(E1, { strategy: 'existing', kindId: 'k9', applyAll: true }); });
    expect(apiMocks.createKindAlias).toHaveBeenCalledWith('tok', {
      alias_code: 'faction', kind_id: 'k9', reassign: true, book_id: BOOK,
    });
    expect(outcome).toEqual({ action: 'merged', count: 2, code: 'faction' });
  });

  it('resolve new + applyAll with a DIFFERENT code mints the kind then aliases', async () => {
    apiMocks.createKind.mockResolvedValue({ kind_id: 'k-new' });
    const { result } = await mountHook([E1, E2]);
    await act(async () => { await result.current.resolve(E1, { strategy: 'new', code: 'sect', name: 'Sect', applyAll: true }); });
    expect(apiMocks.createKind).toHaveBeenCalledWith('tok', { code: 'sect', name: 'Sect' });
    expect(apiMocks.createKindAlias).toHaveBeenCalledWith('tok', expect.objectContaining({ alias_code: 'faction', kind_id: 'k-new' }));
  });

  it('resolve new + applyAll with code == source merges via the unbounded alias endpoint', async () => {
    // The BE skips the redundant alias row (code already owns the new kind) but still
    // reassigns every parked sibling server-side — the FE always routes merge here so
    // the move is unbounded, never limited to the loaded ≤500 snapshot.
    apiMocks.createKind.mockResolvedValue({ kind_id: 'k-new' });
    apiMocks.createKindAlias.mockResolvedValue({ alias_id: '', alias_code: 'faction', kind_id: 'k-new', reassigned: 2 });
    const { result } = await mountHook([E1, E2, E_NOCODE]);
    let outcome;
    await act(async () => { outcome = await result.current.resolve(E1, { strategy: 'new', code: 'faction', name: 'Faction', applyAll: true }); });
    expect(apiMocks.createKind).toHaveBeenCalledWith('tok', { code: 'faction', name: 'Faction' });
    expect(apiMocks.createKindAlias).toHaveBeenCalledWith('tok', { alias_code: 'faction', kind_id: 'k-new', reassign: true, book_id: BOOK });
    expect(apiMocks.reassignEntityKind).not.toHaveBeenCalled();
    expect(outcome).toEqual({ action: 'merged', count: 2, code: 'faction' });
  });

  it('resolve new + single mints the kind then reassigns just the entity', async () => {
    apiMocks.createKind.mockResolvedValue({ kind_id: 'k-new' });
    const { result } = await mountHook([E_NOCODE]);
    await act(async () => { await result.current.resolve(E_NOCODE, { strategy: 'new', code: 'item', name: 'Item', applyAll: false }); });
    expect(apiMocks.createKind).toHaveBeenCalledWith('tok', { code: 'item', name: 'Item' });
    expect(apiMocks.reassignEntityKind).toHaveBeenCalledWith(BOOK, 'e3', 'k-new', 'tok');
    expect(apiMocks.createKindAlias).not.toHaveBeenCalled();
  });
});
