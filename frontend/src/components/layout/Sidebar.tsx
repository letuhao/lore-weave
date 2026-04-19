import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  BookOpen,
  Brain,
  MessageCircle,
  Search,
  BarChart3,
  Settings,
  LogOut,
  LogIn,
  Trophy,
  Trash2,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Moon,
  Sunset,
  Monitor,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { useSidebar } from '@/providers/SidebarProvider';
import { useAppTheme, type AppTheme } from '@/providers/ThemeProvider';
import { cn } from '@/lib/utils';
import { apiJson } from '@/api';
import { NotificationBell } from '@/components/notifications/NotificationBell';

type NavItem = { to: string; icon: React.ElementType; labelKey: string; auth?: boolean };

// auth: true = only show when logged in, undefined = always show
const mainNav: NavItem[] = [
  { to: '/books', icon: BookOpen, labelKey: 'nav.workspace', auth: true },
  { to: '/chat', icon: MessageCircle, labelKey: 'nav.chat', auth: true },
  // K8.1-R1: `to` is `/knowledge` (not `/knowledge/projects`) so NavLink's
  // `startsWith(to + '/')` match keeps the entry active across all
  // tab sub-routes. The /knowledge path itself redirects to /projects.
  { to: '/knowledge', icon: Brain, labelKey: 'nav.knowledge', auth: true },
  { to: '/browse', icon: Search, labelKey: 'nav.browse' },
];

const manageNav: NavItem[] = [
  { to: '/trash', icon: Trash2, labelKey: 'nav.trash', auth: true },
  { to: '/usage', icon: BarChart3, labelKey: 'nav.usage', auth: true },
  { to: '/leaderboard', icon: Trophy, labelKey: 'nav.leaderboard' },
  { to: '/settings/account', icon: Settings, labelKey: 'nav.settings', auth: true },
];

export function Sidebar() {
  const location = useLocation();
  const { t } = useTranslation();
  const { accessToken, user, logoutLocal } = useAuth();
  const { collapsed, toggle } = useSidebar();
  const { appTheme, setAppTheme, themes } = useAppTheme();
  const isLoggedIn = !!accessToken;

  const themeIcons: Record<AppTheme, React.ElementType> = { dark: Moon, light: Sun, sepia: Sunset, oled: Monitor };
  const ThemeIcon = themeIcons[appTheme];
  const cycleTheme = () => {
    const order: AppTheme[] = ['dark', 'light', 'sepia', 'oled'];
    const next = order[(order.indexOf(appTheme) + 1) % order.length];
    setAppTheme(next);
  };

  const handleLogout = async () => {
    if (accessToken) {
      try {
        await apiJson('/v1/auth/logout', { method: 'POST', token: accessToken });
      } catch { /* still clear local */ }
    }
    logoutLocal();
  };

  return (
    <aside
      className={cn(
        'flex flex-col border-r bg-background transition-[width] duration-200',
        collapsed ? 'w-[56px]' : 'w-[240px]',
      )}
    >
      {/* Logo + collapse toggle — always on the same row */}
      <div className={cn('flex items-center py-5', collapsed ? 'flex-col gap-3 px-2' : 'px-4')}>
        <Link to="/" className={cn('flex items-center', collapsed ? '' : 'gap-2.5')}>
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            L
          </div>
          {!collapsed && (
            <span className="font-serif text-base font-semibold tracking-tight">
              LoreWeave
            </span>
          )}
        </Link>
        <button
          onClick={toggle}
          className={cn(
            'rounded p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground',
            !collapsed && 'ml-auto',
          )}
          title={collapsed
            ? t('nav.expand_sidebar', { defaultValue: 'Expand sidebar' })
            : t('nav.collapse_sidebar', { defaultValue: 'Collapse sidebar' })
          }
        >
          {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </button>
      </div>

      {/* Main nav */}
      <nav className="flex-1 space-y-1 px-2">
        {!collapsed && (
          <p className="px-3 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t('nav.main')}
          </p>
        )}
        {collapsed && <div className="pt-2" />}
        {mainNav.filter((i) => !i.auth || isLoggedIn).map((item) => (
          <NavLink
            key={item.to}
            item={item}
            label={t(item.labelKey)}
            currentPath={location.pathname}
            collapsed={collapsed}
          />
        ))}

        {/* Manage section */}
        {manageNav.some((i) => !i.auth || isLoggedIn) && !collapsed && (
          <p className="px-3 pb-1 pt-5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t('nav.manage')}
          </p>
        )}
        {collapsed && manageNav.some((i) => !i.auth || isLoggedIn) && (
          <div className="mx-2 my-3 border-t" />
        )}
        {manageNav.filter((i) => !i.auth || isLoggedIn).map((item) => (
          <NavLink
            key={item.to}
            item={item}
            label={t(item.labelKey)}
            currentPath={location.pathname}
            collapsed={collapsed}
          />
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t p-3">
        {/* Theme toggle — always visible */}
        <div className={cn('mb-2', collapsed ? 'flex justify-center' : 'px-2')}>
          <button
            onClick={cycleTheme}
            className={cn(
              'flex items-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground',
              collapsed ? 'justify-center p-2' : 'w-full gap-3 px-3 py-2 text-sm',
            )}
            title={`Theme: ${themes.find((t) => t.value === appTheme)?.label ?? appTheme}`}
          >
            <ThemeIcon className="h-4 w-4 flex-shrink-0" />
            {!collapsed && (
              <span className="capitalize">{appTheme}</span>
            )}
          </button>
        </div>

        {accessToken ? (
          <>
            {/* Notification bell */}
            {!collapsed && <NotificationBell />}

            {/* Logged-in user */}
            <div className={cn(
              'flex items-center rounded-md',
              collapsed ? 'flex-col gap-2 px-0 py-2' : 'gap-3 px-2 py-2',
            )}>
              <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-primary/20 text-xs font-medium text-primary">
                {(user?.display_name ?? user?.email ?? 'U').charAt(0).toUpperCase()}
              </div>
              {!collapsed && (
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{user?.display_name ?? user?.email ?? 'User'}</p>
                </div>
              )}
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
            {collapsed ? (
              <Link
                to="/login"
                className="flex items-center justify-center rounded-md bg-primary p-2 text-primary-foreground transition-colors hover:bg-primary/90"
                title={t('login.submit', { ns: 'auth', defaultValue: 'Sign In' })}
              >
                <LogIn className="h-4 w-4" />
              </Link>
            ) : (
              <>
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
              </>
            )}
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
  collapsed,
}: {
  item: { to: string; icon: React.ElementType };
  label: string;
  currentPath: string;
  collapsed: boolean;
}) {
  const isActive =
    currentPath === item.to || currentPath.startsWith(item.to + '/');
  const Icon = item.icon;

  return (
    <Link
      to={item.to}
      title={collapsed ? label : undefined}
      className={cn(
        'flex items-center rounded-md text-sm transition-colors',
        collapsed ? 'justify-center px-0 py-2' : 'gap-3 px-3 py-2',
        isActive
          ? 'bg-primary/15 text-primary'
          : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
      )}
    >
      <Icon className="h-4 w-4 flex-shrink-0" />
      {!collapsed && label}
    </Link>
  );
}
