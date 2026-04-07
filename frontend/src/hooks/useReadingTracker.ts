/**
 * GA4-inspired reading tracker hook.
 *
 * ZERO useState — all metrics stored in refs.
 * ZERO re-renders — tracking is invisible to React.
 * Flushes via navigator.sendBeacon() on visibilitychange / pagehide / unmount.
 *
 * Tracks:
 * - time_spent_ms: active reading time (excludes hidden/minimized tab)
 * - scroll_depth: high-water mark (0.0 to 1.0)
 */
import { useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:3000';

interface TrackerConfig {
  bookId: string;
  chapterId: string;
  accessToken?: string | null;
  /** Minimum time (ms) before flushing — avoids noise from quick navigation */
  minFlushMs?: number;
}

export function useReadingTracker({ bookId, chapterId, accessToken, minFlushMs = 2000 }: TrackerConfig) {
  const engageStart = useRef(performance.now());
  const totalSpent = useRef(0);
  const maxScrollDepth = useRef(0);
  const flushed = useRef(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // Stable refs for config (avoid effect re-runs)
  const configRef = useRef({ bookId, chapterId, accessToken, minFlushMs });
  configRef.current = { bookId, chapterId, accessToken, minFlushMs };

  useEffect(() => {
    // Reset on chapter change
    engageStart.current = performance.now();
    totalSpent.current = 0;
    maxScrollDepth.current = 0;
    flushed.current = false;

    // ── Scroll depth via IntersectionObserver ────────────────────────
    let observer: IntersectionObserver | null = null;
    const scrollContainer = document.querySelector('[data-reader-content]');

    if (scrollContainer) {
      // Observe positions at 25%, 50%, 75%, 100% of content height
      const thresholds = [0, 0.25, 0.5, 0.75, 1.0];
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              const ratio = entry.intersectionRatio;
              if (ratio > maxScrollDepth.current) {
                maxScrollDepth.current = ratio;
              }
            }
          }
        },
        { root: scrollContainer as Element, threshold: thresholds },
      );
      // Observe the sentinel at the bottom of content
      if (sentinelRef.current) {
        observer.observe(sentinelRef.current);
      }
    }

    // Fallback: simple scroll-based depth tracking
    const handleScroll = () => {
      const el = scrollContainer || document.documentElement;
      if (el instanceof HTMLElement) {
        const scrollTop = el.scrollTop;
        const scrollHeight = el.scrollHeight - el.clientHeight;
        if (scrollHeight > 0) {
          const depth = Math.min(1, scrollTop / scrollHeight);
          if (depth > maxScrollDepth.current) {
            maxScrollDepth.current = depth;
          }
        }
      }
    };
    (scrollContainer || window).addEventListener('scroll', handleScroll, { passive: true });

    // ── Visibility tracking ─────────────────────────────────────────
    const handleVisibility = () => {
      if (document.hidden) {
        // Tab hidden — accumulate time and flush
        totalSpent.current += performance.now() - engageStart.current;
        flush();
      } else {
        // Tab visible again — reset engage start
        engageStart.current = performance.now();
        flushed.current = false;
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    // pagehide — last chance before tab/window closes
    const handlePageHide = () => {
      totalSpent.current += performance.now() - engageStart.current;
      flush();
    };
    window.addEventListener('pagehide', handlePageHide);

    // ── Flush function ──────────────────────────────────────────────
    function flush() {
      if (flushed.current) return;
      const { bookId, chapterId, accessToken, minFlushMs } = configRef.current;
      const timeSpent = Math.round(totalSpent.current);
      if (timeSpent < minFlushMs) return; // too short, skip

      flushed.current = true;
      const payload = JSON.stringify({
        time_spent_ms: timeSpent,
        scroll_depth: Math.round(maxScrollDepth.current * 100) / 100,
      });

      const url = `${API_BASE}/v1/books/${bookId}/chapters/${chapterId}/progress`;

      // fetch with keepalive — survives page close like sendBeacon,
      // but supports Authorization header (sendBeacon cannot set headers)
      if (accessToken) {
        fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${accessToken}`,
          },
          body: payload,
          keepalive: true,
        }).catch(() => {}); // best-effort
      }
    }

    // ── Cleanup ─────────────────────────────────────────────────────
    return () => {
      // Final flush on unmount (chapter navigation)
      totalSpent.current += performance.now() - engageStart.current;
      flush();

      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('pagehide', handlePageHide);
      (scrollContainer || window).removeEventListener('scroll', handleScroll);
      observer?.disconnect();
    };
  }, [bookId, chapterId]); // re-run when chapter changes

  return sentinelRef;
}
