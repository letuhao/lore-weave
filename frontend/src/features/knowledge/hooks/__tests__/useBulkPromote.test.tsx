import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useBulkPromote } from '../useBulkPromote';
import { knowledgeApi, type Entity } from '../../api';

// C10 — bulk-promote MUST reuse the C9 single-promote endpoint
// (knowledgeApi.promoteEntity), sequentially, reporting progress and
// surviving a single-item failure without aborting the rest.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function fakeEntity(id: string): Entity {
  return {
    id,
    user_id: 'u1',
    project_id: 'p1',
    name: id,
    canonical_name: id,
    kind: 'character',
    aliases: [],
    canonical_version: 1,
    source_types: [],
    confidence: 0.9,
    glossary_entity_id: 'g-' + id,
    anchor_score: 1.0,
    archived_at: null,
    archive_reason: null,
    status: 'canonical',
    evidence_count: 0,
    mention_count: 100,
    user_edited: false,
    version: 1,
    created_at: null,
    updated_at: null,
  };
}

describe('useBulkPromote', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('promotes each selected entity sequentially via the C9 promoteEntity', async () => {
    const calls: string[] = [];
    const spy = vi
      .spyOn(knowledgeApi, 'promoteEntity')
      .mockImplementation(async (id: string) => {
        calls.push(id);
        return fakeEntity(id);
      });

    const { result } = renderHook(() => useBulkPromote(), { wrapper });

    await act(async () => {
      await result.current.run(['e1', 'e2', 'e3']);
    });

    // reused the C9 endpoint, once per selected gap
    expect(spy).toHaveBeenCalledTimes(3);
    // sequential, in order
    expect(calls).toEqual(['e1', 'e2', 'e3']);
    // progress reflects all succeeded
    expect(result.current.progress).toEqual({ done: 3, total: 3, failed: 0 });
    expect(result.current.failures).toEqual([]);
  });

  it('survives a single-item failure and continues the rest', async () => {
    vi.spyOn(knowledgeApi, 'promoteEntity').mockImplementation(
      async (id: string) => {
        if (id === 'bad') throw new Error('boom');
        return fakeEntity(id);
      },
    );

    const { result } = renderHook(() => useBulkPromote(), { wrapper });

    await act(async () => {
      await result.current.run(['ok1', 'bad', 'ok2']);
    });

    // all three were attempted (failure did not abort)
    expect(result.current.progress).toEqual({ done: 3, total: 3, failed: 1 });
    // the failed item is reported, not swallowed
    expect(result.current.failures.map((f) => f.entityId)).toEqual(['bad']);
    expect(result.current.succeeded).toEqual(['ok1', 'ok2']);
  });

  it('reports progress incrementally and settles when complete', async () => {
    // onItemSuccess fires once per completed item, in order — proof the
    // loop advances item-by-item (the progress indicator's data source).
    const completedOrder: string[] = [];
    vi.spyOn(knowledgeApi, 'promoteEntity').mockImplementation(
      async (id: string) => fakeEntity(id),
    );

    const { result } = renderHook(
      () =>
        useBulkPromote({
          onItemSuccess: (e) => completedOrder.push(e.id),
        }),
      { wrapper },
    );

    await act(async () => {
      await result.current.run(['a', 'b']);
    });

    await waitFor(() => expect(result.current.isRunning).toBe(false));
    expect(completedOrder).toEqual(['a', 'b']);
    expect(result.current.progress).toEqual({ done: 2, total: 2, failed: 0 });
  });
});
