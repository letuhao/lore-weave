import { Outlet } from 'react-router-dom';

export function EditorLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Collapsed sidebar (icon-only) — will be built in P2-05 */}
      <aside className="flex w-14 flex-col items-center border-r bg-background py-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
          L
        </div>
      </aside>
      <div className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
