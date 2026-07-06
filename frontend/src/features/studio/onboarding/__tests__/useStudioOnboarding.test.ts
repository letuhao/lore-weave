import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useStudioOnboarding } from '../useStudioOnboarding';
import { STUDIO_ONBOARDING_SEEN_PREF_KEY, STUDIO_ROLE_PREF_KEY } from '../types';

const authMock = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/auth', () => authMock);

const syncPrefsMock = vi.hoisted(() => ({
  loadPrefFromServer: vi.fn(),
  savePrefToServer: vi.fn(),
}));
vi.mock('@/lib/syncPrefs', () => syncPrefsMock);

describe('useStudioOnboarding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authMock.useAuth.mockReturnValue({ accessToken: 'tok' });
    syncPrefsMock.savePrefToServer.mockResolvedValue(true);
  });

  it('isLoading stays true until both prefs resolve; no token never resolves', async () => {
    authMock.useAuth.mockReturnValue({ accessToken: null });
    const { result } = renderHook(() => useStudioOnboarding());
    expect(result.current.isLoading).toBe(true);
    expect(result.current.shouldShow).toBe(false); // never shows before auth resolves
  });

  it('shouldShow becomes true when the seen-flag is unset (first run)', async () => {
    syncPrefsMock.loadPrefFromServer.mockImplementation((key: string) =>
      key === STUDIO_ONBOARDING_SEEN_PREF_KEY ? Promise.resolve(undefined) : Promise.resolve(undefined),
    );
    const { result } = renderHook(() => useStudioOnboarding());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.shouldShow).toBe(true);
    expect(result.current.role).toBeNull();
  });

  it('shouldShow stays false when already seen; role is loaded', async () => {
    syncPrefsMock.loadPrefFromServer.mockImplementation((key: string) => {
      if (key === STUDIO_ONBOARDING_SEEN_PREF_KEY) return Promise.resolve(true);
      if (key === STUDIO_ROLE_PREF_KEY) return Promise.resolve('translator');
      return Promise.resolve(undefined);
    });
    const { result } = renderHook(() => useStudioOnboarding());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.shouldShow).toBe(false);
    expect(result.current.role).toBe('translator');
  });

  it('chooseRole persists both keys and dismisses', async () => {
    syncPrefsMock.loadPrefFromServer.mockResolvedValue(undefined);
    const { result } = renderHook(() => useStudioOnboarding());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { result.current.chooseRole('worldbuilder'); });

    expect(syncPrefsMock.savePrefToServer).toHaveBeenCalledWith(STUDIO_ONBOARDING_SEEN_PREF_KEY, true, 'tok');
    expect(syncPrefsMock.savePrefToServer).toHaveBeenCalledWith(STUDIO_ROLE_PREF_KEY, 'worldbuilder', 'tok');
  });

  it('skip persists only the seen-flag, never traps the user, leaves role untouched', async () => {
    syncPrefsMock.loadPrefFromServer.mockResolvedValue(undefined);
    const { result } = renderHook(() => useStudioOnboarding());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.shouldShow).toBe(true);

    await act(async () => { result.current.skip(); });

    expect(syncPrefsMock.savePrefToServer).toHaveBeenCalledWith(STUDIO_ONBOARDING_SEEN_PREF_KEY, true, 'tok');
    expect(syncPrefsMock.savePrefToServer).not.toHaveBeenCalledWith(STUDIO_ROLE_PREF_KEY, expect.anything(), 'tok');
    expect(result.current.role).toBeNull();
  });

  it('reopen shows the overlay again without re-flipping the seen flag', async () => {
    syncPrefsMock.loadPrefFromServer.mockImplementation((key: string) =>
      Promise.resolve(key === STUDIO_ONBOARDING_SEEN_PREF_KEY ? true : 'writer'),
    );
    const { result } = renderHook(() => useStudioOnboarding());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.shouldShow).toBe(false);

    act(() => { result.current.reopen(); });
    expect(result.current.shouldShow).toBe(true);
    // reopen alone never calls savePrefToServer — only chooseRole/skip do.
    expect(syncPrefsMock.savePrefToServer).not.toHaveBeenCalled();
  });
});
