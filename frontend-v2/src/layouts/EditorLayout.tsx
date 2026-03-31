import { Link, Outlet, useLocation, useParams } from 'react-router-dom';
import { BookOpen, MessageCircle, Settings, LogOut, ChevronLeft } from 'lucide-react';
import { useAuth } from '@/auth';
import { apiJson } from '@/api';
import { cn } from '@/lib/utils';

export function EditorLayout() {
  const { bookId } = useParams();
  const location = useLocation();
  const { accessToken, user, logoutLocal } = useAuth();

  const handleLogout = async () => {
    if (accessToken) {
      try { await apiJson('/v1/auth/logout', { method: 'POST', token: accessToken }); }
      catch { /* still clear local */ }
    }
    logoutLocal();
  };

  const isActive = (to: string) =>
    location.pathname === to || location.pathname.startsWith(to + '/');

  const iconBtn = (to: string, Icon: React.ElementType, label: string) => (
    <Link
      to={to}
      title={label}
      className={cn(
        'flex items-center justify-center rounded-md p-2 transition-colors',
        isActive(to)
          ? 'bg-primary/15 text-primary'
          : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
      )}
    >
      <Icon className="h-4 w-4" />
    </Link>
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="flex w-14 flex-shrink-0 flex-col items-center border-r bg-background py-3">

        {/* Logo */}
        <Link
          to="/"
          title="Home"
          className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground hover:bg-primary/90"
        >
          L
        </Link>

        {/* Back to book — primary editor action */}
        {bookId && (
          <div className="mt-3 w-full px-2">
            <Link
              to={`/books/${bookId}`}
              title="Back to book"
              className="flex w-full items-center justify-center rounded-md p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <ChevronLeft className="h-4 w-4" />
            </Link>
          </div>
        )}

        <div className="mt-2 w-full px-2">
          <div className="mx-auto h-px w-6 bg-border" />
        </div>

        {/* Main nav */}
        <nav className="mt-2 flex w-full flex-col gap-1 px-2">
          {iconBtn('/books', BookOpen, 'Workspace')}
          {iconBtn('/chat', MessageCircle, 'Chat')}
        </nav>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Bottom nav */}
        <div className="flex w-full flex-col gap-1 px-2">
          {iconBtn('/settings/account', Settings, 'Settings')}

          {accessToken ? (
            <>
              {/* User avatar */}
              <Link
                to="/settings/account"
                title={user?.display_name ?? user?.email ?? 'Account'}
                className="flex items-center justify-center rounded-full p-1 transition-colors hover:bg-secondary"
              >
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/20 text-[10px] font-medium text-primary">
                  {(user?.display_name ?? user?.email ?? 'U').charAt(0).toUpperCase()}
                </div>
              </Link>

              {/* Logout */}
              <button
                onClick={() => void handleLogout()}
                title="Log out"
                className="flex w-full items-center justify-center rounded-md p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </>
          ) : (
            <Link
              to="/login"
              title="Sign in"
              className="flex w-full items-center justify-center rounded-md bg-primary p-2 text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <BookOpen className="h-4 w-4" />
            </Link>
          )}
        </div>
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
