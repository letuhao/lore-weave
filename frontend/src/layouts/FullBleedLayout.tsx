import { Outlet } from 'react-router-dom';

export function FullBleedLayout() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <Outlet />
    </div>
  );
}
