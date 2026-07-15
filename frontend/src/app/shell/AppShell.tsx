import { Outlet } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import { MobileTabBar } from './MobileTabBar';
import { useIsMobile } from '@/hooks/useIsMobile';
import { cn } from '@/lib/utils';

// AppShell — the ONE shell that wraps every dashboard/chat route. It solves the
// viewport-remount bug (spec D-MOB-2 / MB1 / MB6): the feature route tree lives under a
// SINGLE persistent `<Outlet/>` and only the CHROME around it swaps at the breakpoint —
// never a top-level `<Mobile/> : <Desktop/>` ternary that would re-instantiate the whole
// subtree (killing the chat SSE stream, voice AudioContext, and unsaved input on a
// tablet rotate or a desktop-window drag).
//
// Why the Outlet survives the flip: the child slots are position-stable —
//   [ Sidebar|false , <main>…<Outlet/>… , MobileTabBar|false ]
// React reconciles children by index, so slot 1 (`main` and its Outlet subtree) is
// PRESERVED across an isMobile change; only slot 0 (desktop Sidebar) and slot 2 (mobile
// tab bar) mount/unmount, and the root div + main change className only (flex-row↔col,
// padding). Exactly ONE chrome's tree is ever live — the inert chrome is not
// CSS-hidden-but-mounted, so there's no double-SSE / double proactive-turn (MB6).
//
// `variant` distinguishes the padded, max-width dashboard body from the full-bleed chat
// body — a className difference on the SAME `main > div > Outlet` chain, so it does not
// change the structure the Outlet hangs from.
export function AppShell({ variant = 'dashboard' }: { variant?: 'dashboard' | 'chat' }) {
  const isMobile = useIsMobile();

  return (
    <div className={cn('flex h-screen overflow-hidden', isMobile ? 'flex-col' : 'flex-row')}>
      {/* slot 0 — desktop chrome */}
      {!isMobile && <Sidebar />}

      {/* slot 1 — the single persistent Outlet (same main>div>Outlet chain in every mode) */}
      <main
        className={cn(
          'min-w-0 flex-1',
          variant === 'chat' && !isMobile ? 'overflow-hidden' : 'overflow-y-auto',
        )}
      >
        <div
          className={cn(
            // Chat fills the frame (children manage their own scroll); dashboard uses
            // min-h-full so it fills a short viewport but GROWS with tall content — keeping
            // its bottom padding after the content instead of pinning to viewport height
            // (a plain h-full regressed the dashboard bottom padding — cold-review M2).
            variant === 'chat' ? 'h-full' : 'min-h-full',
            variant === 'dashboard' && !isMobile && 'mx-auto max-w-6xl px-6 py-6 lg:px-10 lg:py-8',
            variant === 'dashboard' && isMobile && 'px-4 py-4',
          )}
        >
          <Outlet />
        </div>
      </main>

      {/* slot 2 — mobile chrome */}
      {isMobile && <MobileTabBar />}
    </div>
  );
}
