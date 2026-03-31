import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useEditorPanels } from '../useEditorPanels';

describe('useEditorPanels', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns default state when localStorage is empty', () => {
    const { result } = renderHook(() => useEditorPanels());
    expect(result.current.left).toBe(true);
    expect(result.current.right).toBe(true);
    expect(result.current.leftWidth).toBe(300);
    expect(result.current.rightWidth).toBe(320);
  });

  it('reads initial state from localStorage', () => {
    localStorage.setItem('lw_editor_panels', JSON.stringify({
      left: false, right: true, leftWidth: 250, rightWidth: 400,
    }));
    const { result } = renderHook(() => useEditorPanels());
    expect(result.current.left).toBe(false);
    expect(result.current.leftWidth).toBe(250);
    expect(result.current.rightWidth).toBe(400);
  });

  it('handles corrupted localStorage gracefully', () => {
    localStorage.setItem('lw_editor_panels', 'not-json');
    const { result } = renderHook(() => useEditorPanels());
    expect(result.current.left).toBe(true);
    expect(result.current.right).toBe(true);
  });

  it('toggleLeft flips left panel visibility and persists', () => {
    const { result } = renderHook(() => useEditorPanels());
    act(() => result.current.toggleLeft());
    expect(result.current.left).toBe(false);
    const saved = JSON.parse(localStorage.getItem('lw_editor_panels')!);
    expect(saved.left).toBe(false);
  });

  it('toggleRight flips right panel visibility and persists', () => {
    const { result } = renderHook(() => useEditorPanels());
    act(() => result.current.toggleRight());
    expect(result.current.right).toBe(false);
    const saved = JSON.parse(localStorage.getItem('lw_editor_panels')!);
    expect(saved.right).toBe(false);
  });
});
