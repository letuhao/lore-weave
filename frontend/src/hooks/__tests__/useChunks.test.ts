import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChunks } from '../useChunks';

describe('useChunks', () => {
  it('splits text into chunks by double newline', () => {
    const { result } = renderHook(() => useChunks('Hello\n\nWorld\n\nFoo'));
    expect(result.current.chunks).toHaveLength(3);
    expect(result.current.chunks[0]).toEqual({ index: 0, text: 'Hello', dirty: false });
    expect(result.current.chunks[1]).toEqual({ index: 1, text: 'World', dirty: false });
    expect(result.current.chunks[2]).toEqual({ index: 2, text: 'Foo', dirty: false });
  });

  it('returns single empty chunk for empty/whitespace text', () => {
    const { result } = renderHook(() => useChunks(''));
    expect(result.current.chunks).toHaveLength(1);
    expect(result.current.chunks[0].text).toBe('');
  });

  it('handles triple+ newlines as single separator', () => {
    const { result } = renderHook(() => useChunks('A\n\n\n\nB'));
    expect(result.current.chunks).toHaveLength(2);
    expect(result.current.chunks[0].text).toBe('A');
    expect(result.current.chunks[1].text).toBe('B');
  });

  it('starts with isDirty=false', () => {
    const { result } = renderHook(() => useChunks('Hello\n\nWorld'));
    expect(result.current.isDirty).toBe(false);
  });

  it('updateChunk marks chunk as dirty', () => {
    const { result } = renderHook(() => useChunks('Hello\n\nWorld'));
    act(() => {
      result.current.updateChunk(0, 'Changed');
    });
    expect(result.current.chunks[0].text).toBe('Changed');
    expect(result.current.chunks[0].dirty).toBe(true);
    expect(result.current.isDirty).toBe(true);
    // Other chunk unchanged
    expect(result.current.chunks[1].dirty).toBe(false);
  });

  it('reassemble joins chunks with double newline', () => {
    const { result } = renderHook(() => useChunks('A\n\nB\n\nC'));
    act(() => {
      result.current.updateChunk(1, 'Modified');
    });
    expect(result.current.reassemble()).toBe('A\n\nModified\n\nC');
  });

  it('toggleSelect selects and deselects chunks', () => {
    const { result } = renderHook(() => useChunks('A\n\nB\n\nC'));
    // Select chunk 0
    act(() => result.current.toggleSelect(0, false));
    expect(result.current.selected.has(0)).toBe(true);
    expect(result.current.selected.size).toBe(1);

    // Deselect chunk 0
    act(() => result.current.toggleSelect(0, false));
    expect(result.current.selected.has(0)).toBe(false);
  });

  it('toggleSelect with shift adds to selection', () => {
    const { result } = renderHook(() => useChunks('A\n\nB\n\nC'));
    act(() => result.current.toggleSelect(0, false));
    act(() => result.current.toggleSelect(2, true));
    expect(result.current.selected.has(0)).toBe(true);
    expect(result.current.selected.has(2)).toBe(true);
    expect(result.current.selected.size).toBe(2);
  });

  it('clearSelection empties the selection set', () => {
    const { result } = renderHook(() => useChunks('A\n\nB'));
    act(() => result.current.toggleSelect(0, false));
    act(() => result.current.clearSelection());
    expect(result.current.selected.size).toBe(0);
  });

  it('reset re-splits text and clears selection', () => {
    const { result } = renderHook(() => useChunks('A\n\nB'));
    act(() => {
      result.current.updateChunk(0, 'Changed');
      result.current.toggleSelect(0, false);
    });
    act(() => result.current.reset('X\n\nY\n\nZ'));
    expect(result.current.chunks).toHaveLength(3);
    expect(result.current.chunks[0].text).toBe('X');
    expect(result.current.isDirty).toBe(false);
    expect(result.current.selected.size).toBe(0);
  });
});
