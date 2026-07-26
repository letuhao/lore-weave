// M3 view — the "You" screen (the Account tab). Profile + a 7-day usage snapshot + quick links +
// the All-apps drawer + sign-out. Bound to useAuth + useAccountUsage (logic) — view only.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Settings, BarChart3, Shield, LogOut, Grid3x3, ChevronRight, KeyRound, Palette, Library, Bell } from 'lucide-react';
import { useAuth } from '@/auth';
import { apiJson } from '@/api';
import { cn } from '@/lib/utils';
import { useSheetRoute } from '@/components/shared/Sheet';
import { useAccountBudget } from '../hooks/useAccountBudget';
import { AllAppsDrawer, APPS_SHEET_ID } from './AllAppsDrawer';
import { PushSettingsSheet, NOTIFICATIONS_SHEET_ID } from '@/features/push/PushSettingsSheet';
import { pushApi } from '@/features/push/api';

export function YouPage() {
  const { user, accessToken, logoutLocal } = useAuth();
  const { openSheet } = useSheetRoute();
  const budget = useAccountBudget();
  const [signingOut, setSigningOut] = useState(false);

  const signOut = async () => {
    setSigningOut(true);
    // M5 (§8-B2) — remove THIS device's push subscription BEFORE clearing the JWT, so a signed-out
    // device stops buzzing ("Signing out removes this device"). Best-effort; never blocks sign-out.
    try {
      if ('serviceWorker' in navigator) {
        const reg = await navigator.serviceWorker.getRegistration();
        const sub = await reg?.pushManager.getSubscription();
        if (sub && accessToken) {
          await pushApi.unregister(accessToken, sub.endpoint).catch(() => {});
          await sub.unsubscribe().catch(() => {});
        }
      }
    } catch {
      /* ignore — sign-out proceeds regardless */
    }
    if (accessToken) {
      try {
        await apiJson('/v1/auth/logout', { method: 'POST', token: accessToken });
      } catch {
        /* still clear local */
      }
    }
    logoutLocal();
  };

  const name = user?.display_name || user?.email || 'You';
  const initial = name.charAt(0).toUpperCase();

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-4 pb-6" data-testid="you-page">
      {/* Profile */}
      <div className="flex items-center gap-3">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/20 text-xl font-semibold text-primary">
          {initial}
        </div>
        <div className="min-w-0">
          <div className="truncate font-serif text-lg font-semibold">{name}</div>
          {user?.email && <div className="truncate text-sm text-muted-foreground">{user.email}</div>}
        </div>
      </div>

      {/* This month's usage — a budget bar (spent / monthly limit), draft-faithful */}
      <section className="rounded-xl border border-border bg-card p-4" data-testid="you-budget">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">This month&apos;s usage</h2>
          <Link to="/usage" className="flex items-center gap-1 text-xs text-primary">
            Details <ChevronRight className="h-3 w-3" />
          </Link>
        </div>
        {budget.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <div className="flex items-baseline justify-between">
              <span className="text-lg font-semibold tabular-nums">${budget.spent.toFixed(2)}</span>
              <span className="text-sm text-muted-foreground tabular-nums">
                {budget.limit > 0 ? `of $${budget.limit.toFixed(0)}` : 'no cap set'}
              </span>
            </div>
            {budget.limit > 0 && (
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted" data-testid="you-budget-bar">
                <div
                  className={cn('h-full rounded-full', budget.spent / budget.limit >= 0.9 ? 'bg-destructive' : 'bg-primary')}
                  style={{ width: `${Math.min(100, (budget.spent / Math.max(budget.limit, 0.01)) * 100)}%` }}
                />
              </div>
            )}
          </>
        )}
      </section>


      {/* Quick links — every destination is a real, distinct route (no dead links). */}
      <nav className="flex flex-col overflow-hidden rounded-xl border border-border bg-card">
        <Row to="/books" icon={Library} label="Workspaces" note={`${budget.bookCount} ${budget.bookCount === 1 ? 'book' : 'books'}`} />
        <Row onClick={() => openSheet(APPS_SHEET_ID)} icon={Grid3x3} label="All apps" testid="you-all-apps" />
        <Row onClick={() => openSheet(NOTIFICATIONS_SHEET_ID)} icon={Bell} label="Notifications" note="Nudges · per-category · content-free" testid="you-notifications" />
        {/* The assistant hosts the private-data controls (what-I-know, forget, erase everything). */}
        <Row to="/assistant" icon={Shield} label="Assistant data & privacy" />
        <Row to="/settings/providers" icon={KeyRound} label="Models & keys" note="Your BYOK providers" />
        <Row to="/settings/language" icon={Palette} label="Appearance" note="Theme · language · text size" />
        <Row to="/usage" icon={BarChart3} label="Usage & billing" />
        <Row to="/settings/account" icon={Settings} label="Account settings" />
      </nav>

      <button
        type="button"
        data-testid="you-sign-out"
        disabled={signingOut}
        onClick={() => void signOut()}
        className="flex min-h-[44px] items-center justify-center gap-2 rounded-xl border border-border text-sm font-medium text-destructive disabled:opacity-50"
      >
        <LogOut className="h-4 w-4" aria-hidden="true" />
        {signingOut ? 'Signing out…' : 'Sign out'}
      </button>

      <AllAppsDrawer />
      <PushSettingsSheet />
    </div>
  );
}

function Row({
  to,
  onClick,
  icon: Icon,
  label,
  note,
  testid,
}: {
  to?: string;
  onClick?: () => void;
  icon: React.ElementType;
  label: string;
  note?: string;
  testid?: string;
}) {
  const inner = (
    <>
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="block text-sm">{label}</span>
        {note && <span className="block truncate text-[11px] text-muted-foreground">{note}</span>}
      </span>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
    </>
  );
  const cls = 'flex min-h-[48px] items-center gap-3 border-b border-border px-4 last:border-b-0 hover:bg-secondary';
  if (to) {
    return (
      <Link to={to} className={cls} data-testid={testid}>
        {inner}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className={cls + ' w-full text-left'} data-testid={testid}>
      {inner}
    </button>
  );
}
