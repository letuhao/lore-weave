import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { usePdfImportState } from '../usePdfImportState';

describe('usePdfImportState', () => {
  it('starts on the upload step', () => {
    const { result } = renderHook(() => usePdfImportState());
    expect(result.current.state.step).toBe('upload');
    expect(result.current.state.stepIndex).toBe(0);
  });

  it('goNext/goBack move through the fixed step sequence', () => {
    const { result } = renderHook(() => usePdfImportState());
    act(() => result.current.goNext());
    expect(result.current.state.step).toBe('configure');
    act(() => result.current.goNext());
    expect(result.current.state.step).toBe('confirm');
    act(() => result.current.goBack());
    expect(result.current.state.step).toBe('configure');
  });

  it('goNext does not overrun the last step', () => {
    const { result } = renderHook(() => usePdfImportState());
    act(() => {
      for (let i = 0; i < 10; i++) result.current.goNext();
    });
    expect(result.current.state.step).toBe('results');
  });

  it('setFile clears any prior peek result (new file needs a fresh peek)', () => {
    const { result } = renderHook(() => usePdfImportState());
    const file = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    act(() => result.current.setPeekResult(10, null));
    expect(result.current.state.pageCount).toBe(10);
    act(() => result.current.setFile(file));
    expect(result.current.state.pageCount).toBeNull();
    expect(result.current.state.peeked).toBe(false);
  });

  it('setPeekResult with an error clears pageCount and sets peeked=false', () => {
    const { result } = renderHook(() => usePdfImportState());
    act(() => result.current.setPeekResult(null, 'cannot open PDF: password-protected'));
    expect(result.current.state.pageCount).toBeNull();
    expect(result.current.state.peeked).toBe(false);
    expect(result.current.state.peekError).toBe('cannot open PDF: password-protected');
  });

  it('setPagesPerChunk floors to a minimum of 1 (server-side floor is book-service; this is the UI clamp)', () => {
    const { result } = renderHook(() => usePdfImportState());
    act(() => result.current.setPagesPerChunk(0));
    expect(result.current.state.pagesPerChunk).toBe(1);
    act(() => result.current.setPagesPerChunk(-5));
    expect(result.current.state.pagesPerChunk).toBe(1);
    act(() => result.current.setPagesPerChunk(7));
    expect(result.current.state.pagesPerChunk).toBe(7);
  });

  it('defaults pagesPerChunk to 5', () => {
    const { result } = renderHook(() => usePdfImportState());
    expect(result.current.state.pagesPerChunk).toBe(5);
  });

  it('reset() returns to the upload step and clears everything', () => {
    const { result } = renderHook(() => usePdfImportState());
    act(() => {
      result.current.setPeekResult(12, null);
      result.current.setCaptionImages(true);
      result.current.goToStep('results');
    });
    expect(result.current.state.step).toBe('results');
    act(() => result.current.reset());
    expect(result.current.state.step).toBe('upload');
    expect(result.current.state.pageCount).toBeNull();
    expect(result.current.state.captionImages).toBe(false);
  });
});
