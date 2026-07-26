import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Home, Plus, NotebookPen, Library, User } from 'lucide-react';
import { cn } from '@/lib/utils';

// MobileTabBar — the mobile bottom navigation (spec D-MOB-2 / §9 #1). Five tabs; the
// CENTRE is the Work Assistant, raised, because the assistant is the mobile front door.
// "Create" stays an ordinary tab (the sealed decision was what the CENTRE is, not whether
// Create exists). Rendered only by AppShell under the mobile chrome — never mounted
// alongside the desktop Sidebar (MB6: exactly one chrome live).

type Tab = {
  to: string;
  icon: React.ElementType;
  labelKey: string;
  center?: boolean;
  testid: string;
};

// Targets point at real routes (or the M0 placeholders /home, /you that M2/M3 fill in),
// so no tab is a dead link. Labels reuse i18n keys that ALREADY EXIST in every locale
// (parity-verified: nav.home, common.create, nav.assistant, nav.workspace, nav.account),
// so there is no 18-locale sweep and no raw-key leakage. `MOBILE_TAB_LABEL_KEYS` is
// exported so a test can assert each key actually resolves (guards the missing-key bug).
export const MOBILE_TAB_LABEL_KEYS = [
  'nav.home',
  'common.create',
  'nav.assistant',
  'nav.workspace',
  'nav.account',
] as const;

const TABS: Tab[] = [
  { to: '/home', icon: Home, labelKey: 'nav.home', testid: 'mobiletab-home' },
  { to: '/onboarding/new', icon: Plus, labelKey: 'common.create', testid: 'mobiletab-create' },
  { to: '/assistant', icon: NotebookPen, labelKey: 'nav.assistant', center: true, testid: 'mobiletab-assistant' },
  { to: '/books', icon: Library, labelKey: 'nav.workspace', testid: 'mobiletab-library' },
  { to: '/you', icon: User, labelKey: 'nav.account', testid: 'mobiletab-you' },
];

export function MobileTabBar() {
  const location = useLocation();
  const { t } = useTranslation();

  const isActive = (to: string) =>
    location.pathname === to || location.pathname.startsWith(to + '/');

  return (
    <nav
      aria-label={t('nav.main')}
      data-testid="mobile-tab-bar"
      className="flex items-stretch justify-around border-t bg-background pb-[env(safe-area-inset-bottom)]"
    >
      {TABS.map((tab) => {
        const Icon = tab.icon;
        const active = isActive(tab.to);
        const label = t(tab.labelKey);
        return (
          <Link
            key={tab.to}
            to={tab.to}
            data-testid={tab.testid}
            aria-label={label}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'flex min-h-[44px] flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[10px] font-medium transition-colors',
              tab.center && '-mt-4',
              active ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <span
              className={cn(
                'flex items-center justify-center',
                tab.center
                  ? 'h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-lg'
                  : 'h-6 w-6',
                tab.center && active && 'ring-2 ring-primary/40',
              )}
            >
              <Icon className={cn(tab.center ? 'h-6 w-6' : 'h-5 w-5')} aria-hidden="true" />
            </span>
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
