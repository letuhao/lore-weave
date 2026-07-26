import { AppShell } from '@/app/shell/AppShell';

// DashboardLayout — the padded, max-width app body (Sidebar on desktop, bottom tabs on
// mobile). All chrome/viewport logic lives in AppShell (one persistent Outlet, chrome-only
// swap); this is just the dashboard variant selector.
export function DashboardLayout() {
  return <AppShell variant="dashboard" />;
}
