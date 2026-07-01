import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWorkmode } from '../useWorkmode';

describe('useWorkmode', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to write when localStorage is empty', () => {
    const { result } = renderHook(() => useWorkmode());
    expect(result.current[0]).toBe('write');
  });

  it('reads a persisted mode from localStorage', () => {
    localStorage.setItem('lw_editor_workmode', 'translate');
    const { result } = renderHook(() => useWorkmode());
    expect(result.current[0]).toBe('translate');
  });

  it('ignores an unknown persisted value and falls back to write', () => {
    // 'read' is intentionally NOT a workmode (it navigates to the reader route),
    // so a stale/garbage value must not stick.
    localStorage.setItem('lw_editor_workmode', 'read');
    const { result } = renderHook(() => useWorkmode());
    expect(result.current[0]).toBe('write');
  });

  it('setMode updates state and persists', () => {
    const { result } = renderHook(() => useWorkmode());
    act(() => result.current[1]('compose'));
    expect(result.current[0]).toBe('compose');
    expect(localStorage.getItem('lw_editor_workmode')).toBe('compose');
  });
});
