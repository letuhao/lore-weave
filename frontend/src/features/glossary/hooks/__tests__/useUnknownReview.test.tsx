import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { UnknownEntity } from '../../types';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const apiMocks = vi.hoisted(() => ({
  listUnknownEntities: vi.fn(),
  reassignEntityKind: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: apiMocks }));

// The kind is minted on the BOOK tier now. `glossaryApi.createKind` (POST /kinds) and
// `createKindAlias` (POST /kind-aliases) were removed by SS-4 and live-probe at 405 — these tests
// used to mock them and pass, which is exactly how a dead route stays hidden behind green.
const tierMocks = vi.hoisted(() => ({ createBookKind: vi.fn() }));
vi.mock('../../tieringApi', () => ({ tieringApi: tierMocks }));

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
  tierMocks.createBookKind.mockReset();
  apiMocks.reassignEntityKind.mockResolvedValue({ entity_id: 'x', kind_id: 'k' });
  tierMocks.createBookKind.mockResolvedValue({ book_kind_id: 'bk-new', code: 'faction', name: 'Faction' });
});

describe('useUnknownReview', () => {
  it('loads the unknown queue for the book', async () => {
    const { result } = await mountHook([E1]);
    expect(apiMocks.listUnknownEntities).toHaveBeenCalledWith(BOOK, 'tok');
    expect(result.current.items).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('resolve existing reassigns just the entity and invalidates', async () => {
    const { result, invalidateSpy } = await mountHook([E1, E2]);
    let outcome;
    await act(async () => { outcome = await result.current.resolve(E1, { strategy: 'existing', kindId: 'k9' }); });
    expect(apiMocks.reassignEntityKind).toHaveBeenCalledWith(BOOK, 'e1', 'k9', 'tok');
    expect(outcome).toEqual({ action: 'reassigned', name: '哪吒' });
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['glossary-unknown', BOOK]);
    expect(keys).toContainEqual(['glossary-entities', BOOK]);
    expect(keys).toContainEqual(['glossary-kinds']);
  });

  // The 405 that broke this flow. `POST /kinds` was removed by SS-4 (GET still works, which is why
  // it went unnoticed) — so "new kind" could never succeed. The replacement is not a judgement
  // call: `reassign-kind` validates its target against `book_kinds WHERE book_kind_id = $1 AND
  // book_id = $2`, so the BOOK tier is the only id space the very next call would accept.
  it('resolve new mints a BOOK-tier kind and reassigns onto its book_kind_id', async () => {
    const { result } = await mountHook([E_NOCODE]);
    let outcome;
    await act(async () => {
      outcome = await result.current.resolve(E_NOCODE, { strategy: 'new', code: 'item', name: 'Item' });
    });
    expect(tierMocks.createBookKind).toHaveBeenCalledWith(BOOK, { code: 'item', name: 'Item' }, 'tok');
    expect(apiMocks.reassignEntityKind).toHaveBeenCalledWith(BOOK, 'e3', 'bk-new', 'tok');
    expect(outcome).toEqual({ action: 'reassigned', name: '番天印' });
  });

  it('resolving an entity that HAS a source code still moves only that entity', async () => {
    // The bulk "apply to all" went with the alias write (SS-4 removed it; SS-7 brings it back).
    // Until then a sibling sharing the code is NOT silently swept along — the author resolves
    // each one, and the modal says how many are left rather than promising a merge that 405s.
    const { result } = await mountHook([E1, E2]);
    await act(async () => { await result.current.resolve(E1, { strategy: 'existing', kindId: 'k9' }); });
    expect(apiMocks.reassignEntityKind).toHaveBeenCalledTimes(1);
    expect(apiMocks.reassignEntityKind).toHaveBeenCalledWith(BOOK, 'e1', 'k9', 'tok');
  });

});
