// FR / D17 — the erase-everything controller: it calls the API only with a token, surfaces the
// server's boolean honestly, and clears its in-flight flag whichever way the call goes.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const eraseAllData = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({ assistantApi: { eraseAllData: (...a: unknown[]) => eraseAllData(...a) } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useEraseAllData } from '../useEraseAllData';

beforeEach(() => eraseAllData.mockReset());

describe('useEraseAllData (FR)', () => {
  it('erases with the token, returns true on success, and drops the in-flight flag', async () => {
    eraseAllData.mockResolvedValue({ erased: true });
    const { result } = renderHook(() => useEraseAllData());

    let ok = false;
    await act(async () => {
      ok = await result.current.erase();
    });
    expect(eraseAllData).toHaveBeenCalledWith('tok');
    expect(ok).toBe(true);
    expect(result.current.erasing).toBe(false);
  });

  it('returns false and stays honest when the server erases nothing', async () => {
    eraseAllData.mockResolvedValue({ erased: false });
    const { result } = renderHook(() => useEraseAllData());
    let ok = true;
    await act(async () => {
      ok = await result.current.erase();
    });
    expect(ok).toBe(false);
  });

  it('returns false on an API error (the rejection is swallowed, not re-thrown)', async () => {
    eraseAllData.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useEraseAllData());
    // expect().resolves consumes the returned promise — proving erase() RESOLVES to false rather
    // than rejecting (the hook's catch turned the API error into a false + a toast).
    await act(async () => {
      await expect(result.current.erase()).resolves.toBe(false);
    });
    expect(result.current.erasing).toBe(false);
  });
});
