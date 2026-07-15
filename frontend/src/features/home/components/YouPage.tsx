// M3 view — the "You" screen (the Account tab). Profile + a 7-day usage snapshot + quick links +
// the All-apps drawer + sign-out. Bound to useAuth + useAccountUsage (logic) — view only.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Settings, BarChart3, Shield, LogOut, Grid3x3, ChevronRight } from 'lucide-react';
import { useAuth } from '@/auth';
import { apiJson } from '@/api';
import { useSheetRoute } from '@/components/shared/Sheet';
import { useAccountUsage } from '../hooks/useAccountUsage';
import { AllAppsDrawer, APPS_SHEET_ID } from './AllAppsDrawer';
import { PushToggle } from '@/features/push/PushToggle';
import { pushApi } from '@/features/push/api';

export function YouPage() {
  const { user, accessToken, logoutLocal } = useAuth();
  const { openSheet } = useSheetRoute();
  const usage = useAccountUsage();
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

      {/* Usage snapshot (last 7 days) */}
      <section className="rounded-xl border border-border bg-card p-4" data-testid="you-usage">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Last 7 days</h2>
          <Link to="/usage" className="flex items-center gap-1 text-xs text-primary">
            Details <ChevronRight className="h-3 w-3" />
          </Link>
        </div>
        {usage.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : usage.error ? (
          <p className="text-sm text-muted-foreground">Usage unavailable right now.</p>
        ) : (
          <dl className="grid grid-cols-3 gap-2 text-center">
            <Stat label="Requests" value={String(usage.data?.request_count ?? 0)} />
            <Stat label="Tokens" value={compact(usage.data?.total_tokens ?? 0)} />
            <Stat label="Spend" value={`$${(usage.data?.total_cost_usd ?? 0).toFixed(2)}`} />
          </dl>
        )}
      </section>

      {/* Notifications (M5) — self-hides where push isn't available */}
      <PushToggle />

      {/* Quick links — every destination is a real, distinct route (no dead links). */}
      <nav className="flex flex-col overflow-hidden rounded-xl border border-border bg-card">
        <Row onClick={() => openSheet(APPS_SHEET_ID)} icon={Grid3x3} label="All apps" testid="you-all-apps" />
        <Row to="/settings/account" icon={Settings} label="Account settings" />
        <Row to="/usage" icon={BarChart3} label="Usage & billing" />
        {/* The assistant hosts the private-data controls (what-I-know, forget, erase everything). */}
        <Row to="/assistant" icon={Shield} label="Privacy & data" />
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
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-base font-semibold tabular-nums">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function Row({
  to,
  onClick,
  icon: Icon,
  label,
  testid,
}: {
  to?: string;
  onClick?: () => void;
  icon: React.ElementType;
  label: string;
  testid?: string;
}) {
  const inner = (
    <>
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="flex-1 text-sm">{label}</span>
      <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
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

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}
