import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// F2 — useTimezone: needsConfirm until a zone is saved server-side; confirm() writes through to the
// server (SoT) and then hides the affordance.

const loadPref = vi.fn();
const savePref = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: (...a: unknown[]) => loadPref(...a),
  savePrefToServer: (...a: unknown[]) => savePref(...a),
}));

import { useTimezone } from '../useTimezone';

beforeEach(() => {
  loadPref.mockReset();
  savePref.mockReset();
});

describe('useTimezone', () => {
  it('needsConfirm when no zone is saved yet', async () => {
    loadPref.mockResolvedValue(undefined);
    const { result } = renderHook(() => useTimezone());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.needsConfirm).toBe(true);
    expect(result.current.detected).toBeTruthy(); // a browser zone (or UTC fallback)
  });

  it('does NOT need confirm once a zone is saved', async () => {
    loadPref.mockResolvedValue('Europe/London');
    const { result } = renderHook(() => useTimezone());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.needsConfirm).toBe(false);
    expect(result.current.saved).toBe('Europe/London');
  });

  it('confirm() writes through to the server and hides the affordance', async () => {
    loadPref.mockResolvedValue(undefined);
    savePref.mockResolvedValue(true);
    const { result } = renderHook(() => useTimezone());
    await waitFor(() => expect(result.current.needsConfirm).toBe(true));
    await act(async () => {
      await result.current.confirm('Asia/Tokyo');
    });
    expect(savePref).toHaveBeenCalledWith('timezone', 'Asia/Tokyo', 'tok');
    expect(result.current.saved).toBe('Asia/Tokyo');
    expect(result.current.needsConfirm).toBe(false);
  });

  it('a failed save does not mark it confirmed (server is SoT)', async () => {
    loadPref.mockResolvedValue(undefined);
    savePref.mockResolvedValue(false);
    const { result } = renderHook(() => useTimezone());
    await waitFor(() => expect(result.current.needsConfirm).toBe(true));
    await act(async () => {
      await result.current.confirm('Asia/Tokyo');
    });
    expect(result.current.saved).toBeNull();
    expect(result.current.needsConfirm).toBe(true);
  });
});
