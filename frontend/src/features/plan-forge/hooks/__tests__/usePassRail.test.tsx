import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { usePassRail } from '../usePassRail';
import type { PlanPass } from '../../types';

const api = vi.hoisted(() => ({
  listRuns: vi.fn(), passStatus: vi.fn(), runPass: vi.fn(), reviewCheckpoint: vi.fn(), relink: vi.fn(),
}));
vi.mock('../../api', () => ({ planForgeApi: api }));

function pass(over: Partial<PlanPass>): PlanPass {
  return { pass_id: 'motifs', checkpoint: 'advisory', output_kind: 'motif_plan', depends_on: [],
    status: 'pending', decision: 'pending', artifact_id: null, job_id: null, fresh: false, blockers: [], ...over };
}
const ledger = (passes: PlanPass[]) => ({ run_id: 'r1', book_id: 'b1', genre_tags: [], compiled: true, passes, pass_cursor: 0, blocked_at: null });

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  api.listRuns.mockReset().mockResolvedValue({ items: [{ id: 'r1', status: 'checkpoint', created_at: null }], next_cursor: null });
  api.runPass.mockReset().mockResolvedValue({});
  api.reviewCheckpoint.mockReset();
});

describe('usePassRail.runToNextCheckpoint (H2)', () => {
  it('runs the runnable advisory pass, runs the blocking pass, then STOPS for the human', async () => {
    // A state-machine mock keyed on what has actually run (NOT a call counter — react-query's own
    // ledger fetches would otherwise consume the sequence before runToNextCheckpoint starts).
    const done = new Set<string>();
    api.runPass.mockImplementation((_b, _r, passId: string) => { done.add(passId); return Promise.resolve({}); });
    api.passStatus.mockImplementation(() => Promise.resolve(ledger([
      pass({ pass_id: 'motifs', ...(done.has('motifs') ? { status: 'completed', decision: 'auto' } : {}) }),
      pass({ pass_id: 'cast', checkpoint: 'blocking', ...(done.has('cast') ? { status: 'completed', decision: 'pending' } : {}) }),
    ])));

    const { result } = renderHook(() => usePassRail('b1', 'tok'), { wrapper });
    await waitFor(() => expect(result.current.runId).toBe('r1'));
    await act(async () => { await result.current.runToNextCheckpoint('model-1'); });

    const ran = api.runPass.mock.calls.map((c) => c[2]); // 3rd arg = passId
    expect(ran).toContain('motifs');   // the advisory pass ran
    expect(ran).toContain('cast');     // and the blocking pass ran (its ARTIFACT), then we stop
    expect(api.reviewCheckpoint).not.toHaveBeenCalled(); // NEVER auto-approves the checkpoint
  });

  it('stops immediately when a blocking checkpoint is already pending (nothing to run)', async () => {
    api.passStatus.mockResolvedValue(ledger([
      pass({ pass_id: 'motifs', status: 'completed', decision: 'auto' }),
      pass({ pass_id: 'cast', checkpoint: 'blocking', status: 'completed', decision: 'pending' }),
    ]));
    const { result } = renderHook(() => usePassRail('b1', 'tok'), { wrapper });
    await waitFor(() => expect(result.current.runId).toBe('r1'));
    await act(async () => { await result.current.runToNextCheckpoint('model-1'); });
    expect(api.runPass).not.toHaveBeenCalled();
  });
});
