import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { EntityRevisionSummary } from '../../types';

// VG-3 — useEntityRevisions lists an entity's history and restores to a revision.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const apiMocks = vi.hoisted(() => ({
  listEntityRevisions: vi.fn(),
  restoreEntityRevision: vi.fn(),
  getEntityRevision: vi.fn(),
}));
vi.mock('../../api', () => ({ glossaryApi: apiMocks }));

import { useEntityRevisions } from '../useEntityRevisions';

const BOOK = 'book-1';
const ENTITY = 'ent-1';

function rev(num: number, op = 'updated', actor = 'user'): EntityRevisionSummary {
  return {
    revision_id: `r${num}`,
    revision_num: num,
    op,
    actor_type: actor,
    created_at: '2026-06-07T00:00:00Z',
  };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

async function mountHook(revisions: EntityRevisionSummary[]) {
  apiMocks.listEntityRevisions.mockResolvedValue({ revisions });
  const { Wrapper, invalidateSpy } = makeWrapper();
  const { result } = renderHook(() => useEntityRevisions(BOOK, ENTITY), { wrapper: Wrapper });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  return { result, invalidateSpy };
}

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
  apiMocks.restoreEntityRevision.mockResolvedValue({ restored: true, from_revision_num: 2 });
});

describe('useEntityRevisions', () => {
  it('loads the entity revision list (newest first as served)', async () => {
    const { result } = await mountHook([rev(3), rev(2), rev(1, 'baseline', 'system')]);
    expect(apiMocks.listEntityRevisions).toHaveBeenCalledWith(BOOK, ENTITY, 'tok');
    expect(result.current.revisions).toHaveLength(3);
    expect(result.current.revisions[0].revision_num).toBe(3);
  });

  it('restore calls the API and invalidates the revisions query', async () => {
    const { result, invalidateSpy } = await mountHook([rev(2), rev(1)]);
    await act(async () => {
      await result.current.restore('r1');
    });
    expect(apiMocks.restoreEntityRevision).toHaveBeenCalledWith(BOOK, ENTITY, 'r1', 'tok');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['glossary-entity-revisions', BOOK, ENTITY]);
  });
});
