import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import { useProjectSubgraph } from '../useProjectSubgraph';

// C19 adversary MAJOR fix — the shell route re-renders (not remounts) on a
// project switch, so the hook MUST clear its accreted expand-state when the
// (user, project) identity changes, else project A's expansions bleed into
// project B's canvas. This is a wiring test for that reset + the idempotent
// expand guard.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 't', user: { user_id: 'u1' } }) }));

const getProjectSubgraph = vi.fn();
vi.mock('../../api', () => ({ knowledgeApi: { getProjectSubgraph: (...a: unknown[]) => getProjectSubgraph(...a) } }));

const sg = (nodes: string[], cap = false) => ({
  nodes: nodes.map((id) => ({ id, name: id, kind: 'character', anchor_score: 0, mention_count: 1, glossary_entity_id: null })),
  edges: [],
  node_cap_hit: cap,
});

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => { getProjectSubgraph.mockReset(); });

describe('useProjectSubgraph reset + idempotent expand (C19)', () => {
  it('clears accreted expansions when the project changes (no cross-project bleed)', async () => {
    // base for A, then ego(a1) for A's expand, then base for B.
    getProjectSubgraph
      .mockResolvedValueOnce(sg(['a1', 'a2'])) // A base
      .mockResolvedValueOnce(sg(['a1', 'a3'])) // A ego(a1) → adds a3
      .mockResolvedValueOnce(sg(['b1', 'b2'])); // B base

    const { result, rerender } = renderHook(({ pid }) => useProjectSubgraph(pid), {
      wrapper,
      initialProps: { pid: 'A' },
    });
    await waitFor(() => expect(result.current.nodes.map((n) => n.id).sort()).toEqual(['a1', 'a2']));

    await act(async () => { await result.current.expand('a1'); });
    expect(result.current.nodes.map((n) => n.id).sort()).toEqual(['a1', 'a2', 'a3']);
    expect(result.current.expandedIds).toContain('a1');

    // Switch project — the hook stays mounted; accreted MUST reset.
    rerender({ pid: 'B' });
    await waitFor(() => expect(result.current.nodes.map((n) => n.id).sort()).toEqual(['b1', 'b2']));
    expect(result.current.nodes.find((n) => n.id === 'a3')).toBeUndefined(); // A's expansion gone
    expect(result.current.expandedIds).toEqual([]);
  });

  it('expand is idempotent — re-expanding a node fires no second query', async () => {
    getProjectSubgraph
      .mockResolvedValueOnce(sg(['a1', 'a2'])) // base
      .mockResolvedValueOnce(sg(['a1', 'a3'])); // ego(a1)

    const { result } = renderHook(() => useProjectSubgraph('A'), { wrapper });
    await waitFor(() => expect(result.current.nodes.length).toBe(2));

    await act(async () => { await result.current.expand('a1'); });
    const callsAfterFirst = getProjectSubgraph.mock.calls.length;
    await act(async () => { await result.current.expand('a1'); }); // already expanded → no-op
    expect(getProjectSubgraph.mock.calls.length).toBe(callsAfterFirst);
  });
});
