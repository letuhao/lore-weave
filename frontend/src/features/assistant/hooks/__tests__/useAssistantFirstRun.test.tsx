import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const loadPref = vi.fn();
const syncPref = vi.fn();

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: (...a: unknown[]) => loadPref(...a),
  syncPrefsToServer: (...a: unknown[]) => syncPref(...a),
}));

import { ASSISTANT_FIRST_RUN_PREF_KEY, useAssistantFirstRun } from '../useAssistantFirstRun';

beforeEach(() => {
  loadPref.mockReset();
  syncPref.mockReset();
});

describe('useAssistantFirstRun (FR)', () => {
  it('shows the first-run when the flag is unset, and marks done with a server write-through', async () => {
    loadPref.mockResolvedValue(null);
    const { result } = renderHook(() => useAssistantFirstRun());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.shouldShow).toBe(true);

    act(() => result.current.markDone());
    expect(syncPref).toHaveBeenCalledWith(ASSISTANT_FIRST_RUN_PREF_KEY, true, 'tok');
    expect(result.current.shouldShow).toBe(false); // closes immediately
  });

  it('hides the first-run once the account has completed it (multi-device, server-gated)', async () => {
    loadPref.mockResolvedValue(true);
    const { result } = renderHook(() => useAssistantFirstRun());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.shouldShow).toBe(false);
  });
});
