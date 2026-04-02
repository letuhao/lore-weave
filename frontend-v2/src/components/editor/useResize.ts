import { useState, useCallback, useRef } from 'react';

/**
 * Hook for resizing a media block by dragging a corner handle.
 * Returns current width (percentage), setter, and pointer-down handler.
 */
export function useResize(
  initialWidth: number,
  onResizeEnd: (width: number) => void,
  containerRef: React.RefObject<HTMLDivElement | null>,
) {
  const [currentWidth, setCurrentWidth] = useState(initialWidth);
  const isResizing = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      isResizing.current = true;
      startX.current = e.clientX;
      startWidth.current = currentWidth;

      const parentWidth = containerRef.current?.parentElement?.clientWidth ?? 1;

      const onMove = (ev: PointerEvent) => {
        if (!isResizing.current) return;
        const deltaX = ev.clientX - startX.current;
        const deltaPct = (deltaX / parentWidth) * 100;
        const newWidth = Math.round(Math.min(100, Math.max(10, startWidth.current + deltaPct)));
        setCurrentWidth(newWidth);
      };

      const onUp = () => {
        isResizing.current = false;
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
        setCurrentWidth((w) => {
          onResizeEnd(w);
          return w;
        });
      };

      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
    },
    [currentWidth, onResizeEnd, containerRef],
  );

  return { currentWidth, setCurrentWidth, handlePointerDown };
}
