import { Outlet } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';

/**
 * ChatLayout — app sidebar + full-bleed content area.
 * Unlike DashboardLayout, no max-width/padding wrapper.
 * Unlike FullBleedLayout, includes the app sidebar.
 */
export function ChatLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
