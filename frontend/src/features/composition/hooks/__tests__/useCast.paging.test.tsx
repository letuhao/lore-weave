// D-CAST-KEYSET-PAGING (S7) — the cast list is offset-paged, not capped at 200.
// These tests drive the real useInfiniteQuery: a >200 cast reports `hasMore`,
// and `loadMore()` fires a SECOND fetch at the next offset and APPENDS the rows.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { Entity } from '../../../knowledge/api';

const listEntitiesMock = vi.fn();
const getEntityStatusesMock = vi.fn();
vi.mock('../../../knowledge/api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../../knowledge/api');
  return {
    ...actual,
    knowledgeApi: {
      listEntities: (...args: unknown[]) => listEntitiesMock(...args),
      getEntityStatuses: (...args: unknown[]) => getEntityStatusesMock(...args),
    },
  };
});

import { useCast } from '../useCast';

function ent(id: string): Entity {
  return {
    id, user_id: 'u', project_id: 'p', name: id, canonical_name: id, kind: 'character',
    aliases: [], canonical_version: 1, source_types: [], confidence: 0.9, glossary_entity_id: null,
    anchor_score: 0, archived_at: null, archive_reason: null, evidence_count: 1, mention_count: 1,
    user_edited: false, version: 1, created_at: null, updated_at: null,
  } as Entity;
}
const page = (n: number, from: number) =>
  Array.from({ length: n }, (_, i) => ent(`e${from + i}`));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useCast — offset paging (D-CAST-KEYSET-PAGING)', () => {
  beforeEach(() => {
    listEntitiesMock.mockReset();
    getEntityStatusesMock.mockReset();
    getEntityStatusesMock.mockResolvedValue({ statuses: {}, window_available: true });
  });

  it('hasMore=false when the whole cast fits in one page', async () => {
    listEntitiesMock.mockResolvedValue({ entities: page(50, 0), total: 50 });
    const { result } = renderHook(
      () => useCast('proj', 'tok', {}), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.entities.data).toHaveLength(50));
    expect(result.current.hasMore).toBe(false);
    // First (only) fetch pages from offset 0.
    expect(listEntitiesMock).toHaveBeenCalledWith(
      { project_id: 'proj', kind: undefined, search: undefined, limit: 200, offset: 0 },
      'tok',
    );
  });

  it('a >200 cast reports hasMore, and loadMore fetches offset 200 and appends', async () => {
    listEntitiesMock
      .mockResolvedValueOnce({ entities: page(200, 0), total: 250 })
      .mockResolvedValueOnce({ entities: page(50, 200), total: 250 });

    const { result } = renderHook(
      () => useCast('proj', 'tok', {}), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.entities.data).toHaveLength(200));
    expect(result.current.hasMore).toBe(true);
    expect(result.current.total).toBe(250);
    expect(result.current.loaded).toBe(200);

    act(() => { result.current.loadMore(); });

    await waitFor(() => expect(result.current.entities.data).toHaveLength(250));
    // Second fetch used offset=200 (rows loaded so far).
    expect(listEntitiesMock).toHaveBeenNthCalledWith(
      2,
      { project_id: 'proj', kind: undefined, search: undefined, limit: 200, offset: 200 },
      'tok',
    );
    // Flattened in page order — no gaps, no dupes.
    expect(result.current.entities.data!.map((e) => e.id)).toEqual(
      Array.from({ length: 250 }, (_, i) => `e${i}`),
    );
    // Fully drained → no more pages.
    expect(result.current.hasMore).toBe(false);
  });
});
