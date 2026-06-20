import { LogOut } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '@/auth';

const NAV = [
  { to: 'genres', label: 'Genres' },
  { to: 'kinds', label: 'Kinds' },
  { to: 'attributes', label: 'Attributes' },
];

export function CmsShell() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      <aside className="w-56 shrink-0 border-r border-border bg-card flex flex-col">
        <div className="px-4 py-4 border-b border-border">
          <div className="text-sm font-semibold">LoreWeave CMS</div>
          <div className="text-xs text-muted-foreground">System Standards</div>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm ${
                  isActive
                    ? 'bg-secondary text-secondary-foreground'
                    : 'text-muted-foreground hover:bg-secondary/60'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-2 border-t border-border">
          {user?.email && (
            <div className="px-3 pb-2 text-xs text-muted-foreground truncate">{user.email}</div>
          )}
          <button
            onClick={logout}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-secondary/60"
          >
            <LogOut className="h-4 w-4" />
            Log out
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col">
        <div className="border-b border-border bg-destructive/10 px-6 py-2 text-sm text-destructive">
          System Standards — admin only. Changes here affect every tenant.
        </div>
        <div className="flex-1 p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
