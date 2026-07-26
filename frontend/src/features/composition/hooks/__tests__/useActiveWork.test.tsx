import { renderHook, act, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const loadPrefFromServer = vi.fn();
const savePrefToServer = vi.fn();
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: (...a: unknown[]) => loadPrefFromServer(...a),
  savePrefToServer: (...a: unknown[]) => savePrefToServer(...a),
}));

import { useActiveWorkId, useSetActiveWork, activeWorkPrefKey } from '../useActiveWork';

beforeEach(() => {
  loadPrefFromServer.mockReset();
  savePrefToServer.mockReset();
});

describe('useActiveWorkId', () => {
  it('loads the per-book pref on mount (undefined→value)', async () => {
    loadPrefFromServer.mockResolvedValue('deriv-proj');
    const { result } = renderHook(() => useActiveWorkId('book-1', 'tok'));
    expect(result.current.data).toBeUndefined(); // loading
    await waitFor(() => expect(result.current.data).toBe('deriv-proj'));
    expect(loadPrefFromServer).toHaveBeenCalledWith(activeWorkPrefKey('book-1'), 'tok');
  });

  it('stays undefined without a token (no fetch)', () => {
    const { result } = renderHook(() => useActiveWorkId('book-1', null));
    expect(result.current.data).toBeUndefined();
    expect(loadPrefFromServer).not.toHaveBeenCalled();
  });
});

describe('useSetActiveWork (the Switch-to write path)', () => {
  it('writes the pref durably and returns ok', async () => {
    savePrefToServer.mockResolvedValue(true);
    const { result } = renderHook(() => useSetActiveWork('book-1', 'tok'));
    let ok: boolean | undefined;
    await act(async () => { ok = await result.current.switchTo('deriv-proj'); });
    expect(ok).toBe(true);
    expect(savePrefToServer).toHaveBeenCalledWith(activeWorkPrefKey('book-1'), 'deriv-proj', 'tok');
  });

  it('fans the switch out — a mounted useActiveWorkId reloads after a switchTo', async () => {
    // reader mounted with the OLD pref
    loadPrefFromServer.mockResolvedValue('canon-proj');
    const reader = renderHook(() => useActiveWorkId('book-1', 'tok'));
    await waitFor(() => expect(reader.result.current.data).toBe('canon-proj'));

    // switchTo → durable write succeeds → notify → reader re-loads the NEW pref
    savePrefToServer.mockResolvedValue(true);
    loadPrefFromServer.mockResolvedValue('deriv-proj');
    const setter = renderHook(() => useSetActiveWork('book-1', 'tok'));
    await act(async () => { await setter.result.current.switchTo('deriv-proj'); });

    await waitFor(() => expect(reader.result.current.data).toBe('deriv-proj')); // fanned out
  });

  it('a failed durable write does NOT fan out (server is SoT)', async () => {
    loadPrefFromServer.mockResolvedValue('canon-proj');
    const reader = renderHook(() => useActiveWorkId('book-1', 'tok'));
    await waitFor(() => expect(reader.result.current.data).toBe('canon-proj'));

    savePrefToServer.mockResolvedValue(false); // write failed
    loadPrefFromServer.mockResolvedValue('deriv-proj'); // would-be new value, must NOT be read
    const setter = renderHook(() => useSetActiveWork('book-1', 'tok'));
    let ok: boolean | undefined;
    await act(async () => { ok = await setter.result.current.switchTo('deriv-proj'); });
    expect(ok).toBe(false);
    expect(reader.result.current.data).toBe('canon-proj'); // unchanged — no fan-out on failure
  });
});
