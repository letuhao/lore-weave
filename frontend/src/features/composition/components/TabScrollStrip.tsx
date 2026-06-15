import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

// D-080 (cosmetic) — a horizontally-scrollable tab strip with edge FADE
// indicators. The compose panel packs 16 sub-tabs into a narrow, resizable
// column; the strip scrolls but gave NO visual hint that tabs continued
// off-screen. This wraps the scroller and overlays a left/right gradient that
// shows ONLY on the side that has more content (scroll-aware, not always-on),
// so the affordance reads as "there's more this way" and disappears at the ends.
//
// The inner scroller keeps the caller's testid + className (the overflow class)
// so existing structural assertions hold; the fades are pointer-events-none
// decoration over it.
interface Props {
  children: ReactNode;
  className?: string;
  testid?: string;
}

export function TabScrollStrip({ children, className, testid }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [fade, setFade] = useState({ left: false, right: false });

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    // 1px slack so sub-pixel rounding at the extremes doesn't flicker the fade.
    setFade({
      left: scrollLeft > 1,
      right: scrollLeft + clientWidth < scrollWidth - 1,
    });
  }, []);

  useEffect(() => {
    update();
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    // Recompute when the panel is resized (the strip is in a resizable column)
    // or the tab set changes (its content box resizes).
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [update, children]);

  return (
    <div className="relative">
      <div ref={ref} data-testid={testid} className={className} onScroll={update}>
        {children}
      </div>
      {fade.left && (
        <div
          aria-hidden
          data-testid="tab-fade-left"
          className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-background to-transparent"
        />
      )}
      {fade.right && (
        <div
          aria-hidden
          data-testid="tab-fade-right"
          className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-background to-transparent"
        />
      )}
    </div>
  );
}
