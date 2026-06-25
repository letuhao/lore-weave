import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FloatingWindow } from '../FloatingWindow';
import type { Rect } from '../../../workspace/types';

const RECT: Rect = { x: 100, y: 100, w: 400, h: 300 };

function setup(over: Partial<Parameters<typeof FloatingWindow>[0]> = {}) {
  const props = {
    title: 'Compose',
    rect: RECT,
    zIndex: 42,
    onMove: vi.fn(),
    onResize: vi.fn(),
    onDock: vi.fn(),
    onFocus: vi.fn(),
    ...over,
  };
  render(<FloatingWindow {...props}><div data-testid="panel-body">body</div></FloatingWindow>);
  return props;
}

describe('FloatingWindow (T5.4 M3)', () => {
  it('portals to body with the title, children, and fixed geometry', () => {
    setup();
    const win = screen.getByTestId('floating-window');
    expect(win.parentElement).toBe(document.body);              // portaled
    expect(win).toHaveTextContent('Compose');
    expect(screen.getByTestId('panel-body')).toBeInTheDocument();
    expect(win.style.left).toBe('100px');
    expect(win.style.top).toBe('100px');
    expect(win.style.zIndex).toBe('42');
  });

  it('the dock button returns the panel to the dock', () => {
    const p = setup();
    fireEvent.click(screen.getByTestId('floating-window-dock'));
    expect(p.onDock).toHaveBeenCalledTimes(1);
  });

  it('drag follows the cursor visually but commits the rect ONCE on release (no write-storm)', () => {
    const p = setup();
    const win = screen.getByTestId('floating-window');
    fireEvent.pointerDown(screen.getByTestId('floating-window-header'), { clientX: 50, clientY: 50 });
    fireEvent.pointerMove(window, { clientX: 80, clientY: 90 });   // dx=30 dy=40
    // the window FOLLOWS visually during the drag…
    expect(win.style.left).toBe('130px');
    expect(win.style.top).toBe('140px');
    // …but does NOT dispatch on every move (the owner isn't asked to persist mid-drag)
    expect(p.onMove).not.toHaveBeenCalled();
    fireEvent.pointerUp(window, { clientX: 80, clientY: 90 });
    // committed exactly once, with the final rect
    expect(p.onMove).toHaveBeenCalledTimes(1);
    expect(p.onMove).toHaveBeenCalledWith({ x: 130, y: 140, w: 400, h: 300 });
    // after release, further moves are ignored
    p.onMove.mockClear();
    fireEvent.pointerMove(window, { clientX: 200, clientY: 200 });
    expect(p.onMove).not.toHaveBeenCalled();
  });

  it('dragging the SE corner resizes on release, clamped to the minimum', () => {
    const p = setup();
    fireEvent.pointerDown(screen.getByTestId('floating-window-resize'), { clientX: 500, clientY: 400 });
    fireEvent.pointerUp(window, { clientX: 560, clientY: 460 });   // +60 / +60
    expect(p.onResize).toHaveBeenCalledTimes(1);
    expect(p.onResize).toHaveBeenCalledWith({ x: 100, y: 100, w: 460, h: 360 });
  });

  it('resizing far past the floor clamps to MIN_W/MIN_H on release', () => {
    const p = setup();
    fireEvent.pointerDown(screen.getByTestId('floating-window-resize'), { clientX: 500, clientY: 400 });
    fireEvent.pointerUp(window, { clientX: 0, clientY: 0 });        // shrink way past the floor
    expect(p.onResize).toHaveBeenCalledWith({ x: 100, y: 100, w: 280, h: 180 });
  });

  it('focuses (raises) on pointer-down anywhere in the window', () => {
    const p = setup();
    fireEvent.pointerDown(screen.getByTestId('floating-window-header'), { clientX: 50, clientY: 50 });
    expect(p.onFocus).toHaveBeenCalled();
  });

  it('clamps a negative drag to the top-left edge on release (no off-screen)', () => {
    const p = setup();
    fireEvent.pointerDown(screen.getByTestId('floating-window-header'), { clientX: 50, clientY: 50 });
    fireEvent.pointerUp(window, { clientX: -500, clientY: -500 });  // would push x/y < 0
    expect(p.onMove).toHaveBeenCalledWith({ x: 0, y: 0, w: 400, h: 300 });
  });

  it('clamps a far drag so the window can never go fully off-screen (recoverable) (/review-impl MED)', () => {
    const p = setup();   // jsdom viewport is 1024×768; EDGE_MARGIN keeps a grip on-screen
    fireEvent.pointerDown(screen.getByTestId('floating-window-header'), { clientX: 50, clientY: 50 });
    fireEvent.pointerUp(window, { clientX: 5000, clientY: 5000 }); // drag way past the right/bottom edge
    const arg = p.onMove.mock.calls[0][0];
    expect(arg.x).toBeLessThanOrEqual(1024 - 48);   // header still reachable
    expect(arg.y).toBeLessThanOrEqual(768 - 48);
    expect(arg.x).toBeGreaterThan(0);
  });
});
