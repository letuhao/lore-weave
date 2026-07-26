import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { nextSidebarWidth, useSidebarResize } from '../useSidebarResize';
import { SIDEBAR_WIDTH_DEFAULT, clampSidebarWidth, SIDEBAR_WIDTH_MIN, SIDEBAR_WIDTH_MAX } from '../../types';

describe('nextSidebarWidth', () => {
  it('adds the horizontal delta to the drag-start width', () => {
    expect(nextSidebarWidth(260, 100, 140)).toBe(300); // dragged right 40
    expect(nextSidebarWidth(260, 100, 60)).toBe(220);  // dragged left 40
  });
});

describe('clampSidebarWidth', () => {
  it('clamps to [MIN, MAX] and rounds; NaN → default', () => {
    expect(clampSidebarWidth(10)).toBe(SIDEBAR_WIDTH_MIN);
    expect(clampSidebarWidth(9999)).toBe(SIDEBAR_WIDTH_MAX);
    expect(clampSidebarWidth(300.7)).toBe(301);
    expect(clampSidebarWidth(Number.NaN)).toBe(SIDEBAR_WIDTH_DEFAULT);
  });
});

/** A minimal fake pointer event with the capture surface the hook calls. */
const evt = (clientX: number, button = 0) => ({
  button,
  clientX,
  pointerId: 1,
  preventDefault: vi.fn(),
  currentTarget: { setPointerCapture: vi.fn(), releasePointerCapture: vi.fn() },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
}) as any;

describe('useSidebarResize', () => {
  it('reports width live during drag (persist=false), then persists once on pointer-up', () => {
    const onResize = vi.fn();
    const { result } = renderHook(() => useSidebarResize({ width: 260, onResize }));

    act(() => result.current.handleProps.onPointerDown(evt(100)));
    expect(result.current.resizing).toBe(true);

    act(() => result.current.handleProps.onPointerMove(evt(150))); // +50 live
    expect(onResize).toHaveBeenLastCalledWith(310, false);

    act(() => result.current.handleProps.onPointerUp(evt(180)));   // +80 commit
    expect(onResize).toHaveBeenLastCalledWith(340, true);
    expect(result.current.resizing).toBe(false);
  });

  it('ignores a non-primary button and a move before a down', () => {
    const onResize = vi.fn();
    const { result } = renderHook(() => useSidebarResize({ width: 260, onResize }));
    act(() => result.current.handleProps.onPointerMove(evt(150)));       // no active drag
    act(() => result.current.handleProps.onPointerDown(evt(100, 2)));    // right button
    expect(result.current.resizing).toBe(false);
    expect(onResize).not.toHaveBeenCalled();
  });

  it('double-click resets to the default width (persisted)', () => {
    const onResize = vi.fn();
    const { result } = renderHook(() => useSidebarResize({ width: 420, onResize }));
    act(() => result.current.handleProps.onDoubleClick());
    expect(onResize).toHaveBeenCalledWith(SIDEBAR_WIDTH_DEFAULT, true);
  });
});
