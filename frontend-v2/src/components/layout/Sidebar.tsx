import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  BookOpen,
  MessageCircle,
  Search,
  BarChart3,
  Settings,
  LogOut,
  LogIn,
  Bell,
  Trophy,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { cn } from '@/lib/utils';
import { apiJson } from '@/api';

type NavItem = { to: string; icon: React.ElementType; labelKey: string; auth?: boolean };

// auth: true = only show when logged in, undefined = always show
const mainNav: NavItem[] = [
  { to: '/books', icon: BookOpen, labelKey: 'nav.workspace', auth: true },
  { to: '/chat', icon: MessageCircle, labelKey: 'nav.chat', auth: true },
  { to: '/browse', icon: Search, labelKey: 'nav.browse' },
];

const manageNav: NavItem[] = [
  { to: '/usage', icon: BarChart3, labelKey: 'nav.usage', auth: true },
  { to: '/leaderboard', icon: Trophy, labelKey: 'nav.leaderboard' },
  { to: '/settings/account', icon: Settings, labelKey: 'nav.settings', auth: true },
];

export function Sidebar() {
  const location = useLocation();
  const { t } = useTranslation();
  const { accessToken, logoutLocal } = useAuth();
  const isLoggedIn = !!accessToken;

  const handleLogout = async () => {
    if (accessToken) {
      try {
        await apiJson('/v1/auth/logout', { method: 'POST', token: accessToken });
      } catch { /* still clear local */ }
    }
    logoutLocal();
  };

  return (
    <aside className="flex w-[240px] flex-col border-r bg-background">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
          L
        </div>
        <span className="font-serif text-base font-semibold tracking-tight">
          LoreWeave
        </span>
      </div>

      {/* Main nav */}
      <nav className="flex-1 space-y-1 px-2">
        <p className="px-3 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {t('nav.main')}
        </p>
        {mainNav.filter((i) => !i.auth || isLoggedIn).map((item) => (
          <NavLink key={item.to} item={item} label={t(item.labelKey)} currentPath={location.pathname} />
        ))}

        {/* Only show Manage section if at least one item is visible */}
        {manageNav.some((i) => !i.auth || isLoggedIn) && (
          <p className="px-3 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t('nav.manage')}
          </p>
        )}
        {manageNav.filter((i) => !i.auth || isLoggedIn).map((item) => (
          <NavLink key={item.to} item={item} label={t(item.labelKey)} currentPath={location.pathname} />
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t p-3">
        {accessToken ? (
          <>
            {/* Notification bell */}
            <Link
              to="/notifications"
              className="mb-2 flex items-center gap-3 rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <Bell className="h-4 w-4" />
              <span>{t('nav.notifications')}</span>
            </Link>

            {/* Logged-in user */}
            <div className="flex items-center gap-3 rounded-md px-2 py-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/20 text-xs font-medium text-primary">
                U
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">User</p>
              </div>
              <button
                onClick={() => void handleLogout()}
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                title={t('nav.logout')}
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </>
        ) : (
          /* Not logged in — show sign in */
          <div className="space-y-2">
            <Link
              to="/login"
              className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <LogIn className="h-4 w-4" />
              {t('login.submit', { ns: 'auth', defaultValue: 'Sign In' })}
            </Link>
            <Link
              to="/register"
              className="flex w-full items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              {t('register.submit', { ns: 'auth', defaultValue: 'Create Account' })}
            </Link>
          </div>
        )}
      </div>
    </aside>
  );
}

function NavLink({
  item,
  label,
  currentPath,
}: {
  item: { to: string; icon: React.ElementType };
  label: string;
  currentPath: string;
}) {
  const isActive =
    currentPath === item.to || currentPath.startsWith(item.to + '/');
  const Icon = item.icon;

  return (
    <Link
      to={item.to}
      className={cn(
        'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
        isActive
          ? 'bg-primary/15 text-primary'
          : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </Link>
  );
}
