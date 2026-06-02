import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useExtractionState } from '../useExtractionState';

// Regression guard for F-1: the per-chapter "Extract Glossary" flow passes the
// chapter id via preselectedChapterIds. If the hook stops seeding chapterIds from
// it, the single-chapter extraction silently runs over 0 chapters again.
describe('useExtractionState', () => {
  it('single mode seeds chapterIds from preselectedChapterIds', () => {
    const { result } = renderHook(() => useExtractionState('single', ['ch-1']));
    expect(result.current.state.chapterIds).toEqual(['ch-1']);
    // single flow skips the dedicated chapters step
    expect(result.current.state.steps).not.toContain('chapters');
  });

  it('defaults to empty chapterIds when none preselected', () => {
    const { result } = renderHook(() => useExtractionState('single'));
    expect(result.current.state.chapterIds).toEqual([]);
  });

  it('batch mode includes a chapters selection step and starts empty', () => {
    const { result } = renderHook(() => useExtractionState('batch'));
    expect(result.current.state.steps).toContain('chapters');
    expect(result.current.state.chapterIds).toEqual([]);
    act(() => result.current.setChapterIds(['a', 'b']));
    expect(result.current.state.chapterIds).toEqual(['a', 'b']);
  });
});
