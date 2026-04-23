import { useEffect, useState } from 'react';

// K19f.1 — viewport-width hook for the mobile/desktop shell swap in
// KnowledgePage. Mobile = ``< 768px`` per the plan (matches Tailwind's
// default ``md`` breakpoint at 768px).
//
// Synchronous initial read from ``window.matchMedia`` prevents FOUC —
// the first render already knows which shell to paint. Live updates
// via the MediaQueryList ``change`` event handle orientation changes
// and DevTools device-mode toggling.
//
// SSR-safe: ``typeof window === 'undefined'`` short-circuits to
// ``false`` (Vite-SPA doesn't SSR today, but the guard costs nothing
// and keeps the hook transplant-safe).

const MOBILE_MAX_WIDTH = 767; // < 768 — Tailwind md default.
const MEDIA_QUERY = `(max-width: ${MOBILE_MAX_WIDTH}px)`;

function readInitial(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia(MEDIA_QUERY).matches;
}

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState<boolean>(readInitial);

  useEffect(() => {
    if (
      typeof window === 'undefined' ||
      typeof window.matchMedia !== 'function'
    ) {
      return;
    }
    const mql = window.matchMedia(MEDIA_QUERY);
    const onChange = (ev: MediaQueryListEvent) => setIsMobile(ev.matches);
    mql.addEventListener('change', onChange);
    // Mid-lifecycle safety: a matchMedia result can change between
    // the initial synchronous read and the effect running (e.g.
    // tests that toggle viewport between render and effect). Sync
    // once on mount to stay aligned with the current state.
    setIsMobile(mql.matches);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}
