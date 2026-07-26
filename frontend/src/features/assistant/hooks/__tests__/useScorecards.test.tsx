import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// R2 (D-COACHING-SCORECARD-MOUNT) — the hook makes the scorecard reachable + enforces SD-7 fail-closed:
// a card missing `quarantine` normalizes to quarantine=TRUE, and the trend gate excludes quarantine.

const getScorecards = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({ assistantApi: { getScorecards: (...a: unknown[]) => getScorecards(...a) } }));

import { useScorecards } from '../useScorecards';

beforeEach(() => {
  getScorecards.mockReset();
});

describe('useScorecards', () => {
  it('exposes the newest card and normalizes a missing quarantine flag to TRUE (SD-7 fail-closed)', async () => {
    getScorecards.mockResolvedValue({
      scorecards: [
        // newest first; this card OMITS quarantine — must normalize to true, never trended.
        { output_id: 'o2', session_id: 's2', title: 'B', created_at: '2026-07-15',
          card: { overall_score: 80, dimensions: [] } },
        { output_id: 'o1', session_id: 's1', title: 'A', created_at: '2026-07-08',
          card: { overall_score: 60, quarantine: true, dimensions: [] } },
      ],
    });
    const { result } = renderHook(() => useScorecards());
    await waitFor(() => expect(result.current.latest).not.toBeNull());
    expect(result.current.latest?.output_id).toBe('o2');
    expect(result.current.latest?.card.quarantine).toBe(true); // missing flag → fail-closed true
    // both are quarantine → no trend may be drawn (SD-7)
    expect(result.current.showTrend).toBe(false);
    expect(result.current.items).toHaveLength(2);
  });

  it('a genuine quarantine=false card is preserved (only missing/invalid defaults to true)', async () => {
    getScorecards.mockResolvedValue({
      scorecards: [{ output_id: 'o', session_id: null, title: null, created_at: null,
                     card: { overall_score: 90, quarantine: false, dimensions: [] } }],
    });
    const { result } = renderHook(() => useScorecards());
    await waitFor(() => expect(result.current.latest).not.toBeNull());
    expect(result.current.latest?.card.quarantine).toBe(false);
  });

  it('degrades to empty on a fetch failure (no crash)', async () => {
    getScorecards.mockRejectedValue(new Error('down'));
    const { result } = renderHook(() => useScorecards());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toEqual([]);
    expect(result.current.latest).toBeNull();
  });
});
