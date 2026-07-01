import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStudioChrome } from '../useStudioChrome';

const KEY = 'lw_studio_chrome_b1';

describe('useStudioChrome', () => {
  beforeEach(() => localStorage.clear());

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

  it('keys state per book (no cross-book bleed)', () => {
    const a = renderHook(() => useStudioChrome('b1'));
    act(() => a.result.current.setActiveView('quality'));
    const b = renderHook(() => useStudioChrome('b2'));
    expect(b.result.current.activeView).toBe('manuscript'); // b2 untouched
  });
});
