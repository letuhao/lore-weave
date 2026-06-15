import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const getWorldSubgraphMock = vi.fn();
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: { getWorldSubgraph: (...a: unknown[]) => getWorldSubgraphMock(...a) },
}));

import { useWorldSubgraph } from '../useWorldSubgraph';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => getWorldSubgraphMock.mockReset());

describe('useWorldSubgraph (W5/G4)', () => {
  it('fetches the rollup and breaks nodes down per source project (legend)', async () => {
    getWorldSubgraphMock.mockResolvedValue({
      nodes: [
        { id: 'a', name: 'A', kind: 'character', anchor_score: 0, mention_count: 2, glossary_entity_id: null, source_project_id: 'p1' },
        { id: 'b', name: 'B', kind: 'character', anchor_score: 0, mention_count: 1, glossary_entity_id: null, source_project_id: 'p1' },
        { id: 'c', name: 'C', kind: 'location', anchor_score: 0, mention_count: 1, glossary_entity_id: null, source_project_id: 'p2' },
      ],
      edges: [],
      node_cap_hit: false,
    });
    const { result } = renderHook(() => useWorldSubgraph('w1'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getWorldSubgraphMock).toHaveBeenCalledWith('w1', { limit: 200 }, 'tok');
    expect(result.current.nodes).toHaveLength(3);
    // p1 contributed 2 nodes, p2 one → sorted by nodeCount DESC.
    expect(result.current.sources).toEqual([
      { projectId: 'p1', nodeCount: 2 },
      { projectId: 'p2', nodeCount: 1 },
    ]);
    expect(result.current.truncated).toBe(false);
  });

  it('surfaces node_cap_hit as truncated', async () => {
    getWorldSubgraphMock.mockResolvedValue({ nodes: [], edges: [], node_cap_hit: true });
    const { result } = renderHook(() => useWorldSubgraph('w1'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.truncated).toBe(true);
  });

  it('does not fetch when worldId is undefined', async () => {
    const { result } = renderHook(() => useWorldSubgraph(undefined), { wrapper });
    expect(result.current.nodes).toEqual([]);
    expect(getWorldSubgraphMock).not.toHaveBeenCalled();
  });

  it('buckets nodes missing a source into "unknown" (defensive)', async () => {
    getWorldSubgraphMock.mockResolvedValue({
      nodes: [{ id: 'a', name: 'A', kind: 'character', anchor_score: 0, mention_count: 1, glossary_entity_id: null }],
      edges: [],
      node_cap_hit: false,
    });
    const { result } = renderHook(() => useWorldSubgraph('w1'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.sources).toEqual([{ projectId: 'unknown', nodeCount: 1 }]);
  });
});
