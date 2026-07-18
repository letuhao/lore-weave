import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStudioChrome } from '../useStudioChrome';

const KEY = 'lw_studio_chrome_b1';
const isMobileState = vi.hoisted(() => ({ value: false }));
vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: () => isMobileState.value }));

describe('useStudioChrome', () => {
  beforeEach(() => {
    localStorage.clear();
    isMobileState.value = false;
  });

  it('defaults to manuscript / expanded / bottom-closed when empty', () => {
    const { result } = renderHook(() => useStudioChrome('b1'));
    expect(result.current.activeView).toBe('manuscript');
    expect(result.current.sidebarCollapsed).toBe(false);
    expect(result.current.bottomOpen).toBe(false);
  });

  it('loads a persisted state', () => {
    localStorage.setItem(KEY, JSON.stringify({ activeView: 'quality', sidebarCollapsed: true, bottomOpen: true }));
    const { result } = renderHook(() => useStudioChrome('b1'));
    expect(result.current.activeView).toBe('quality');
    expect(result.current.sidebarCollapsed).toBe(true);
    expect(result.current.bottomOpen).toBe(true);
  });

  it('guards a corrupt / unknown-view payload back to defaults', () => {
    localStorage.setItem(KEY, 'not-json');
    expect(renderHook(() => useStudioChrome('b1')).result.current.activeView).toBe('manuscript');
    localStorage.setItem(KEY, JSON.stringify({ activeView: 'bogus' }));
    expect(renderHook(() => useStudioChrome('b1')).result.current.activeView).toBe('manuscript');
  });

  it('setActiveView switches to a different view and persists', () => {
    const { result } = renderHook(() => useStudioChrome('b1'));
    act(() => result.current.setActiveView('bible'));
    expect(result.current.activeView).toBe('bible');
    expect(result.current.sidebarCollapsed).toBe(false);
    expect(JSON.parse(localStorage.getItem(KEY)!).activeView).toBe('bible');
  });

  it('re-clicking the active view (sidebar open) collapses the sidebar', () => {
    const { result } = renderHook(() => useStudioChrome('b1'));
    act(() => result.current.setActiveView('manuscript')); // already active
    expect(result.current.sidebarCollapsed).toBe(true);
    expect(result.current.activeView).toBe('manuscript');
  });

  it('selecting a view while collapsed expands and switches (never leaves it hidden)', () => {
    localStorage.setItem(KEY, JSON.stringify({ activeView: 'manuscript', sidebarCollapsed: true, bottomOpen: false }));
    const { result } = renderHook(() => useStudioChrome('b1'));
    act(() => result.current.setActiveView('search'));
    expect(result.current.activeView).toBe('search');
    expect(result.current.sidebarCollapsed).toBe(false);
  });

  it('toggleSidebar and toggleBottom flip + persist', () => {
    const { result } = renderHook(() => useStudioChrome('b1'));
    act(() => result.current.toggleSidebar());
    expect(result.current.sidebarCollapsed).toBe(true);
    act(() => result.current.toggleBottom());
    expect(result.current.bottomOpen).toBe(true);
    const saved = JSON.parse(localStorage.getItem(KEY)!);
    expect(saved.sidebarCollapsed).toBe(true);
    expect(saved.bottomOpen).toBe(true);
  });

  it('defaults sidebarWidth and loads/clamps a persisted width', () => {
    expect(renderHook(() => useStudioChrome('b1')).result.current.sidebarWidth).toBe(260);
    localStorage.setItem(KEY, JSON.stringify({ activeView: 'manuscript', sidebarWidth: 999999 }));
    expect(renderHook(() => useStudioChrome('b1')).result.current.sidebarWidth).toBe(640); // clamped to MAX
  });

  it('setSidebarWidth clamps; persist=false updates state WITHOUT writing, persist=true writes', () => {
    const { result } = renderHook(() => useStudioChrome('b1'));
    act(() => result.current.setSidebarWidth(120, false)); // below MIN, live (no write)
    expect(result.current.sidebarWidth).toBe(200);
    expect(localStorage.getItem(KEY)).toBeNull(); // live drag frame did NOT persist
    act(() => result.current.setSidebarWidth(340, true)); // commit
    expect(result.current.sidebarWidth).toBe(340);
    expect(JSON.parse(localStorage.getItem(KEY)!).sidebarWidth).toBe(340);
  });

  it('keys state per book (no cross-book bleed)', () => {
    const a = renderHook(() => useStudioChrome('b1'));
    act(() => a.result.current.setActiveView('quality'));
    const b = renderHook(() => useStudioChrome('b2'));
    expect(b.result.current.activeView).toBe('manuscript'); // b2 untouched
  });

  // #16 Phase 4 (M6) — a first-time mobile visit has no persisted preference; the sidebar must
  // default collapsed there (confirmed live: sidebar + activity bar left ~88px of a 390px screen).
  it('defaults the sidebar collapsed on a first mobile visit (no persisted state)', () => {
    isMobileState.value = true;
    const { result } = renderHook(() => useStudioChrome('b1'));
    expect(result.current.sidebarCollapsed).toBe(true);
  });

  it('a returning mobile user\'s persisted choice wins over the mobile default', () => {
    localStorage.setItem(KEY, JSON.stringify({ activeView: 'manuscript', sidebarCollapsed: false, bottomOpen: false }));
    isMobileState.value = true;
    const { result } = renderHook(() => useStudioChrome('b1'));
    expect(result.current.sidebarCollapsed).toBe(false);
  });
});
