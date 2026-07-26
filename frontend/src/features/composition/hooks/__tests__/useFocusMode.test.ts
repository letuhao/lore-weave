import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useFocusMode } from '../useFocusMode';

const KEY = 'loreweave.editor.focusMode';

describe('useFocusMode (T5.1)', () => {
  beforeEach(() => localStorage.clear());

  it('defaults to off when nothing is stored', () => {
    const { result } = renderHook(() => useFocusMode());
    expect(result.current.focusMode).toBe(false);
  });

  it('reads a persisted on-state from localStorage', () => {
    localStorage.setItem(KEY, '1');
    const { result } = renderHook(() => useFocusMode());
    expect(result.current.focusMode).toBe(true);
  });

  it('toggle flips state and persists per-device', () => {
    const { result } = renderHook(() => useFocusMode());
    act(() => result.current.toggle());
    expect(result.current.focusMode).toBe(true);
    expect(localStorage.getItem(KEY)).toBe('1');
    act(() => result.current.toggle());
    expect(result.current.focusMode).toBe(false);
    expect(localStorage.getItem(KEY)).toBe('0');
  });

  it('setFocusMode writes the explicit value', () => {
    const { result } = renderHook(() => useFocusMode());
    act(() => result.current.setFocusMode(true));
    expect(result.current.focusMode).toBe(true);
    expect(localStorage.getItem(KEY)).toBe('1');
  });
});
