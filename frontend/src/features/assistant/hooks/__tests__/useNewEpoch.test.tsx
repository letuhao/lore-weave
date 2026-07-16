// A4 — the new-epoch controller: calls only with a token + bookId, surfaces the server outcome honestly,
// and never lets a rejection escape.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const newEpoch = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({ assistantApi: { newEpoch: (...a: unknown[]) => newEpoch(...a) } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useNewEpoch } from '../useNewEpoch';

beforeEach(() => newEpoch.mockReset());

describe('useNewEpoch (A4)', () => {
  it('closes the epoch with the book id and returns the result', async () => {
    newEpoch.mockResolvedValueOnce({ epoch_closed: true, facts_invalidated: 3, new_project_id: 'p2' });
    const { result } = renderHook(() => useNewEpoch('book-1'));
    let res: unknown;
    await act(async () => { res = await result.current.startNewEpoch(); });
    expect(newEpoch).toHaveBeenCalledWith('tok', { book_id: 'book-1' });
    expect(res).toMatchObject({ epoch_closed: true, facts_invalidated: 3 });
    expect(result.current.starting).toBe(false);
  });

  it('does nothing without a bookId (no call)', async () => {
    const { result } = renderHook(() => useNewEpoch(null));
    let res: unknown = 'x';
    await act(async () => { res = await result.current.startNewEpoch(); });
    expect(newEpoch).not.toHaveBeenCalled();
    expect(res).toBeNull();
  });

  it('returns null on an API error (rejection swallowed)', async () => {
    newEpoch.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useNewEpoch('book-1'));
    await act(async () => {
      await expect(result.current.startNewEpoch()).resolves.toBeNull();
    });
    expect(result.current.starting).toBe(false);
  });
});
