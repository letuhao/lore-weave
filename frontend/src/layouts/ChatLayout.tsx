import { AppShell } from '@/app/shell/AppShell';

/**
 * ChatLayout — full-bleed content area (no max-width/padding wrapper), Sidebar on desktop
 * and bottom tabs on mobile. The assistant + chat surfaces live here. All chrome/viewport
 * logic lives in AppShell (one persistent Outlet, chrome-only swap); this is just the
 * full-bleed variant selector.
 */
export function ChatLayout() {
  return <AppShell variant="chat" />;
}
