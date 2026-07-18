import { useCallback, useRef, useState } from 'react';
import { SIDEBAR_WIDTH_DEFAULT } from '../types';

/** Pure width math for the drag: new width = the width at drag-start + the horizontal delta.
 * Extracted so the clamp-and-commit behaviour is unit-testable without a real pointer. */
export function nextSidebarWidth(startWidth: number, startX: number, clientX: number): number {
  return startWidth + (clientX - startX);
}

interface Options {
  /** Current width (the drag baseline). */
  width: number;
  /** Live update (persist=false) during drag, persisted commit (persist=true) on release/reset. */
  onResize: (width: number, persist: boolean) => void;
}

/**
 * Owns the Side Bar's edge-drag resize. Uses pointer capture so the drag survives the pointer
 * crossing into a dock panel / iframe, and reports width live during the drag but only asks the
 * caller to PERSIST on pointer-up (or a double-click reset) — a mouse-move must not write
 * localStorage on every frame. The hook is self-contained (own refs + cleanup); the component only
 * spreads `handleProps` onto the drag handle and reads `resizing` for cursor/overlay chrome.
 */
export function useSidebarResize({ width, onResize }: Options) {
  const drag = useRef<{ startX: number; startWidth: number } | null>(null);
  const [resizing, setResizing] = useState(false);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLElement>) => {
    // Only the primary button starts a drag; ignore right/middle.
    if (e.button !== 0) return;
    e.preventDefault();
    drag.current = { startX: e.clientX, startWidth: width };
    setResizing(true);
    e.currentTarget.setPointerCapture?.(e.pointerId);
  }, [width]);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLElement>) => {
    if (!drag.current) return;
    onResize(nextSidebarWidth(drag.current.startWidth, drag.current.startX, e.clientX), false);
  }, [onResize]);

  const finish = useCallback((e: React.PointerEvent<HTMLElement>) => {
    if (!drag.current) return;
    onResize(nextSidebarWidth(drag.current.startWidth, drag.current.startX, e.clientX), true);
    drag.current = null;
    setResizing(false);
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  }, [onResize]);

  // Double-click the handle → reset to the default width (VS Code sash behaviour).
  const onDoubleClick = useCallback(() => onResize(SIDEBAR_WIDTH_DEFAULT, true), [onResize]);

  return {
    resizing,
    handleProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp: finish,
      onPointerCancel: finish,
      onDoubleClick,
    },
  };
}
