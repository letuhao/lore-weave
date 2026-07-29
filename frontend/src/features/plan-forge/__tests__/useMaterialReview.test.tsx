// The packet must survive a reload — the search SPENDS, so re-opening the panel must not re-pay.
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const getMissingMaterial = vi.fn();
const findMissingMaterial = vi.fn();
vi.mock('../api', () => ({ planForgeApi: {
  getMissingMaterial: (...a: unknown[]) => getMissingMaterial(...a),
  findMissingMaterial: (...a: unknown[]) => findMissingMaterial(...a),
  keepMaterial: vi.fn(),
} }));

import { useMaterialReview } from '../hooks/useMaterialReview';

const PACKET = {
  version: 1, recovered: [], ask: [], unavailable: [],
  review: [{ kind: 'mechanics', status: 'absent' as const, dropped_ungrounded: 0, note: '',
             candidates: [{ quote: 'Salt only moves by sea.', why: '' }] }],
  read: { failed: false, unclassified: [], note: '' },
};

beforeEach(() => vi.clearAllMocks());

it('loads the LAST packet on mount, without searching', async () => {
  getMissingMaterial.mockResolvedValue(PACKET);
  const { result } = renderHook(() => useMaterialReview('b', 'r', 't'));
  await waitFor(() => expect(result.current.packet).not.toBeNull());
  expect(getMissingMaterial).toHaveBeenCalledWith('b', 'r', 't');
  expect(findMissingMaterial).not.toHaveBeenCalled();   // opening the panel must never spend
  // and the author's keeps are seeded from it, so a reload does not silently drop everything
  expect(result.current.kept).toEqual({ mechanics: ['Salt only moves by sea.'] });
});

it('a run that was never checked leaves the panel idle rather than erroring', async () => {
  getMissingMaterial.mockResolvedValue(null);
  const { result } = renderHook(() => useMaterialReview('b', 'r', 't'));
  await waitFor(() => expect(getMissingMaterial).toHaveBeenCalled());
  expect(result.current.packet).toBeNull();
  expect(result.current.error).toBeNull();
});

it('a failed load is not shown as an error — there may simply be no prior packet', async () => {
  getMissingMaterial.mockRejectedValue(new Error('404'));
  const { result } = renderHook(() => useMaterialReview('b', 'r', 't'));
  await waitFor(() => expect(getMissingMaterial).toHaveBeenCalled());
  expect(result.current.error).toBeNull();
});

it('does not load without a run — the panel mounts before a run is picked', async () => {
  renderHook(() => useMaterialReview('b', null, 't'));
  expect(getMissingMaterial).not.toHaveBeenCalled();
});
