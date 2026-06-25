import { render, screen, fireEvent, act } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkspaceLayoutProvider, useWorkspaceLayout } from '../WorkspaceLayoutContext';

// WS-D server-sync: mock the prefs transport so the localStorage-only tests stay
// unchanged (no token wrapper → these are never called) and the token tests can
// drive hydrate + write-through deterministically.
const { loadMock, syncMock } = vi.hoisted(() => ({ loadMock: vi.fn(), syncMock: vi.fn() }));
vi.mock('@/lib/syncPrefs', () => ({
  loadPrefFromServer: (...a: unknown[]) => loadMock(...a),
  syncPrefsToServer: (...a: unknown[]) => syncMock(...a),
  savePrefToServer: vi.fn(),
}));

const FLAG_KEY = 'loom.workspace.enabled';
const LAYOUT_KEY = 'loom.workspace.layout';

beforeEach(() => { localStorage.clear(); loadMock.mockReset(); syncMock.mockReset(); loadMock.mockResolvedValue(undefined); });

function wrapper({ children }: { children: React.ReactNode }) {
  return <WorkspaceLayoutProvider>{children}</WorkspaceLayoutProvider>;
}
function tokenWrapper({ children }: { children: React.ReactNode }) {
  return <WorkspaceLayoutProvider token="tok">{children}</WorkspaceLayoutProvider>;
}

describe('WorkspaceLayoutContext (T5.4 M1)', () => {
  it('the feature flag defaults OFF', () => {
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    expect(result.current.enabled).toBe(false);
  });

  it('setEnabled flips the flag and persists it per-device', () => {
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    act(() => result.current.setEnabled(true));
    expect(result.current.enabled).toBe(true);
    expect(localStorage.getItem(FLAG_KEY)).toBe('true');
  });

  it('reads the saved flag on mount', () => {
    localStorage.setItem(FLAG_KEY, 'true');
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    expect(result.current.enabled).toBe(true);
  });

  it('starts from the default dock layout (every panel docked, compose active)', () => {
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    expect(result.current.layout.active).toBe('compose');
    expect(result.current.layout.panels.compose?.placement).toBe('dock');
    expect(result.current.layout.panels.references?.placement).toBe('dock');
  });

  it('falls back to the default layout when localStorage is corrupt (never crashes)', () => {
    localStorage.setItem(LAYOUT_KEY, '{ not valid json');
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    expect(result.current.layout.version).toBe(1);
    expect(result.current.layout.active).toBe('compose');
  });

  it('falls back to default when the stored layout has a bad shape', () => {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({ version: 2, panels: {} }));
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    expect(result.current.layout.version).toBe(1);
  });

  it('merges a stale saved layout over the default so NEW panels stay reachable (/review-impl MED)', () => {
    // a layout saved before 'references' existed — only lists a couple of panels
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({
      version: 1, active: 'compose',
      panels: { compose: { placement: 'dock', order: 0 }, cast: { placement: 'dock', order: 1 } },
    }));
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    // the saved entries are kept...
    expect(result.current.layout.panels.compose?.order).toBe(0);
    // ...AND every current panel that was missing gets a default dock entry
    expect(result.current.layout.panels.references?.placement).toBe('dock');
    expect(result.current.layout.panels.settings?.placement).toBe('dock');
  });

  it('a placement dispatch mutates the layout and persists it', () => {
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    act(() => result.current.dispatch({ type: 'set-placement', id: 'cast', placement: 'float', rect: { x: 10, y: 20, w: 300, h: 400 } }));
    expect(result.current.layout.panels.cast?.placement).toBe('float');
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY)!);
    expect(saved.panels.cast.placement).toBe('float');
  });

  it('useWorkspaceLayout throws outside the provider', () => {
    expect(() => renderHook(() => useWorkspaceLayout())).toThrow(/WorkspaceLayoutProvider/);
  });

  // ── WS-D (D-T5.4-SERVER-SYNC) ──
  it('without a token, never touches the server (per-device only)', () => {
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper });
    act(() => result.current.setEnabled(true));
    expect(loadMock).not.toHaveBeenCalled();
    expect(syncMock).not.toHaveBeenCalled();
  });

  it('hydrates {enabled, layout} from the server on login, forward-merging the layout (LWW)', async () => {
    loadMock.mockResolvedValue({
      enabled: true,
      layout: {
        version: 1, active: 'compose',
        panels: { compose: { placement: 'dock', order: 0 }, cast: { placement: 'float', order: 1, rect: { x: 1, y: 2, w: 300, h: 200 } } },
      },
    });
    const { result } = renderHook(() => useWorkspaceLayout(), { wrapper: tokenWrapper });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(loadMock).toHaveBeenCalledWith('loom_workspace', 'tok');
    expect(result.current.enabled).toBe(true);                       // server enabled wins
    expect(result.current.layout.panels.cast?.placement).toBe('float');
    expect(result.current.layout.panels.references?.placement).toBe('dock'); // forward-merge keeps new panels
  });

  it('writes the workspace pref through to the server on change (debounced, LWW)', () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useWorkspaceLayout(), { wrapper: tokenWrapper });
      act(() => result.current.setEnabled(true));
      expect(syncMock).not.toHaveBeenCalled();                       // debounced, not yet
      act(() => { vi.advanceTimersByTime(800); });
      expect(syncMock).toHaveBeenCalledWith('loom_workspace', expect.objectContaining({ enabled: true }), 'tok');
    } finally {
      vi.useRealTimers();
    }
  });

  it('hydrate cancels a write-through armed BEFORE it resolved (no stale post → no divergence)', async () => {
    // /review-impl MED: a user change racing the hydrate must not POST after the
    // server value wins, or server & local diverge.
    let resolveLoad: (v: unknown) => void = () => {};
    loadMock.mockReturnValue(new Promise((r) => { resolveLoad = r; }));
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useWorkspaceLayout(), { wrapper: tokenWrapper });
      act(() => result.current.setEnabled(true));                    // user change → arms the 800ms timer
      await act(async () => { resolveLoad({ enabled: false }); await Promise.resolve(); await Promise.resolve(); });
      expect(result.current.enabled).toBe(false);                    // server won on load
      act(() => { vi.advanceTimersByTime(800); });
      expect(syncMock).not.toHaveBeenCalled();                       // the stale pre-hydrate timer was cancelled
    } finally {
      vi.useRealTimers();
    }
  });
});
