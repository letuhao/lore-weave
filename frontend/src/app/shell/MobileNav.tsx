import { useLocation } from 'react-router-dom';
import { useAuth } from '@/auth';
import { useIsMobile } from '@/hooks/useIsMobile';
import { MobileTabBar } from './MobileTabBar';

// MobileNav — the ALWAYS-VISIBLE mobile bottom navigator. Rendered once at the app root (not inside
// a layout) and fixed to the viewport bottom, so the tab bar is present on every BROWSE/dashboard
// app screen — where a standalone PWA (no browser back) would otherwise strand the user (the
// reported bug). It is HIDDEN on two kinds of route:
//   1. logged-out / non-app routes (auth flow, public share, OS pop-out windows) — a bottom app-nav
//      makes no sense there;
//   2. the focused FULL-SCREEN work surfaces (chapter editor, reader, studio, translation review) —
//      these are immersive, desktop-first, and have their OWN exit chrome; a fixed bar there just
//      OVERLAYS their bottom toolbar/last line with no clearance (cold-review MED-1). They don't go
//      through AppShell (which reserves the clearance), so showing it there is a defect, not a feature.
const HIDE_PREFIXES = [
  '/login',
  '/register',
  '/forgot',
  '/reset',
  '/oauth',
  '/s/', // public shared-book reader
  '/composition/popout',
  '/studio/popout',
];

// Focused full-screen surfaces, matched by path SUFFIX (they're nested under /books/:id/... so a
// prefix match would wrongly also hide the book-detail browse page, which SHOULD keep the nav).
const HIDE_SUFFIXES = ['/edit', '/compare', '/translations', '/read', '/studio'];

function isHidden(pathname: string): boolean {
  if (HIDE_PREFIXES.some((p) => pathname === p || pathname.startsWith(p))) return true;
  if (HIDE_SUFFIXES.some((s) => pathname.endsWith(s))) return true;
  if (pathname.includes('/review/')) return true; // /books/:id/chapters/:cid/review/:versionId
  return false;
}

export function MobileNav() {
  const isMobile = useIsMobile();
  const { accessToken } = useAuth();
  const { pathname } = useLocation();

  if (!isMobile || !accessToken) return null;
  if (isHidden(pathname)) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-40" data-testid="mobile-nav">
      <MobileTabBar />
    </div>
  );
}
