import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useServerPagedList } from '../useServerPagedList';

describe('useServerPagedList', () => {
  it('computes offset/limit from page & pageSize (query input, total-independent)', () => {
    const { result } = renderHook(() => useServerPagedList(50));
    expect(result.current.offset).toBe(0);
    expect(result.current.limit).toBe(50);
    act(() => result.current.setPage(2));
    expect(result.current.offset).toBe(100);
  });

  it('pageInfo derives pageCount + range from the server total', () => {
    const { result } = renderHook(() => useServerPagedList(50));
    act(() => result.current.setPage(2));
    const info = result.current.pageInfo(250);
    expect(info.pageCount).toBe(5);
    expect(info.safePage).toBe(2);
    expect(info.start).toBe(101);
    expect(info.end).toBe(150);
  });

  it('pageInfo clamps the displayed page when total shrinks', () => {
    const { result } = renderHook(() => useServerPagedList(50));
    act(() => result.current.setPage(5));
    const info = result.current.pageInfo(30); // pageCount 1
    expect(info.safePage).toBe(0);
    expect(info.start).toBe(1);
    expect(info.end).toBe(30);
  });

  it('pageInfo on an empty set → pageCount 1, range 0', () => {
    const { result } = renderHook(() => useServerPagedList(50));
    const info = result.current.pageInfo(0);
    expect(info.pageCount).toBe(1);
    expect(info.start).toBe(0);
    expect(info.end).toBe(0);
  });

  it('setPageSize resets to page 0', () => {
    const { result } = renderHook(() => useServerPagedList(50));
    act(() => result.current.setPage(4));
    expect(result.current.offset).toBe(200);
    act(() => result.current.setPageSize(100));
    expect(result.current.pageSize).toBe(100);
    expect(result.current.offset).toBe(0);
    expect(result.current.pageInfo(500).pageCount).toBe(5);
  });

  it('reset jumps back to page 0', () => {
    const { result } = renderHook(() => useServerPagedList(50));
    act(() => result.current.setPage(3));
    act(() => result.current.reset());
    expect(result.current.page).toBe(0);
    expect(result.current.offset).toBe(0);
  });
});
