import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { SyncChange, SyncDiff } from '../../types/ontology';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const availableMock = vi.fn();
const applyMock = vi.fn();
vi.mock('../../api/ontology', () => ({
  ontologyApi: {
    syncAvailable: (...a: unknown[]) => availableMock(...a),
    syncApply: (...a: unknown[]) => applyMock(...a),
  },
}));

import { useOntologySync, changeKey } from '../useOntologySync';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const CHANGES: SyncChange[] = [
  { node_type: 'edge_type', code: 'SWORN_SIBLING_OF', change: 'added' },
  { node_type: 'edge_type', code: 'BETROTHED_TO', change: 'modified', fields_changed: ['cardinality'] },
  { node_type: 'vocab_value', parent_code: 'drive', code: 'obsession', change: 'added' },
];

const DIFF: SyncDiff = {
  source_ref: 'system:xianxia-harem',
  source_hash_current: 'hash-new',
  project_source_hash: 'hash-old',
  has_updates: true,
  changes: CHANGES,
};

beforeEach(() => {
  availableMock.mockReset().mockResolvedValue(DIFF);
  applyMock.mockReset().mockResolvedValue({ schema_version: 4, source_hash: 'hash-new', applied: 2 });
});

describe('useOntologySync', () => {
  it('keyed decisions do not collide across node types/parents', () => {
    expect(changeKey(CHANGES[0])).toBe('edge_type::SWORN_SIBLING_OF');
    expect(changeKey(CHANGES[2])).toBe('vocab_value:drive:obsession');
  });

  it('defaults each change to keep_mine until set', async () => {
    const { result } = renderHook(() => useOntologySync('p1'), { wrapper });
    await waitFor(() => expect(result.current.changes).toHaveLength(3));
    expect(result.current.getChoice(CHANGES[0])).toBe('keep_mine');
    expect(result.current.decidedCount).toBe(0);
  });

  it('records per-node decisions and only sends explicitly-set ones', async () => {
    const { result } = renderHook(() => useOntologySync('p1'), { wrapper });
    await waitFor(() => expect(result.current.changes).toHaveLength(3));

    act(() => result.current.setDecision(CHANGES[0], 'take_theirs'));
    act(() => result.current.setDecision(CHANGES[1], 'keep_mine'));

    expect(result.current.getChoice(CHANGES[0])).toBe('take_theirs');
    expect(result.current.decidedCount).toBe(2);
    expect(result.current.pendingDecisions).toEqual([
      { node_type: 'edge_type', parent_code: null, code: 'SWORN_SIBLING_OF', choice: 'take_theirs' },
      { node_type: 'edge_type', parent_code: null, code: 'BETROTHED_TO', choice: 'keep_mine' },
    ]);
  });

  it('takeAllTheirs / keepAllMine set every change', async () => {
    const { result } = renderHook(() => useOntologySync('p1'), { wrapper });
    await waitFor(() => expect(result.current.changes).toHaveLength(3));

    act(() => result.current.takeAllTheirs());
    expect(result.current.decidedCount).toBe(3);
    expect(result.current.pendingDecisions.every((d) => d.choice === 'take_theirs')).toBe(true);

    act(() => result.current.keepAllMine());
    expect(result.current.pendingDecisions.every((d) => d.choice === 'keep_mine')).toBe(true);
  });

  it('apply posts base_source_hash + decisions and clears local state', async () => {
    const { result } = renderHook(() => useOntologySync('p1'), { wrapper });
    await waitFor(() => expect(result.current.changes).toHaveLength(3));

    act(() => result.current.setDecision(CHANGES[2], 'take_theirs'));
    await act(async () => {
      await result.current.apply();
    });

    expect(applyMock).toHaveBeenCalledWith(
      'p1',
      {
        base_source_hash: 'hash-new',
        decisions: [
          { node_type: 'vocab_value', parent_code: 'drive', code: 'obsession', choice: 'take_theirs' },
        ],
      },
      'tok',
    );
    await waitFor(() => expect(result.current.decidedCount).toBe(0));
    expect(result.current.applyResult?.applied).toBe(2);
  });
});
