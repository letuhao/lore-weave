import { useEffect, useState } from 'react';

// Shared mobile/desktop viewport hook (hoisted from features/knowledge for the LOOM
// composition mobile pass — composition + knowledge now share one source). Mobile =
// `< 768px` (Tailwind's default `md` breakpoint).
//
// Synchronous initial read from `window.matchMedia` prevents FOUC — the first render
// already knows which shell to paint. Live updates via the MediaQueryList `change`
// event handle orientation changes and DevTools device-mode toggling.
//
// SSR-safe: `typeof window === 'undefined'` short-circuits to `false`.

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
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }
    const mql = window.matchMedia(MEDIA_QUERY);
    const onChange = (ev: MediaQueryListEvent) => setIsMobile(ev.matches);
    mql.addEventListener('change', onChange);
    // Mid-lifecycle safety: a matchMedia result can change between the initial
    // synchronous read and the effect running; sync once on mount.
    setIsMobile(mql.matches);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return isMobile;
}
