import { useTranslation } from 'react-i18next';
import { Loader2, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { domainScope } from '@/features/settings/api';
import type { useOAuthConsent } from '../hooks/useOAuthConsent';

type Consent = ReturnType<typeof useOAuthConsent>;

const chipCls = (on: boolean) =>
  cn(
    'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors',
    on ? 'border-primary bg-primary/5' : 'opacity-60 hover:bg-secondary',
  );

/** Render-only consent card. All logic lives in useOAuthConsent. */
export function OAuthConsentView(c: Consent) {
  const { t } = useTranslation('oauth');

  if (!c.valid) {
    return <Card>{<p className="text-sm text-destructive">{t('consent.invalid_request')}</p>}</Card>;
  }

  if (c.needsLogin) {
    return (
      <Card>
        <Header />
        <p className="mt-4 text-sm text-muted-foreground">{t('consent.subtitle')}</p>
        <button onClick={c.goLogin} className="mt-5 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          {t('consent.sign_in')}
        </button>
      </Card>
    );
  }

  return (
    <Card>
      <Header />
      <p className="mt-3 text-sm text-muted-foreground">
        {c.params.clientName
          ? t('consent.client_named', { client: c.params.clientName })
          : t('consent.client_unnamed')}
      </p>
      {c.userEmail && (
        <p className="mt-1 text-xs text-muted-foreground">{t('consent.signed_in_as', { email: c.userEmail })}</p>
      )}

      <div className="mt-5">
        <p className="text-sm font-medium">{t('consent.permissions_heading')}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{t('consent.permissions_hint')}</p>

        {c.tiers.length > 0 && (
          <>
            <p className="mt-3 mb-1 text-xs font-medium text-muted-foreground">{t('consent.actions_heading')}</p>
            <div className="grid grid-cols-1 gap-2">
              {c.tiers.map((tier) => (
                <label key={tier} className={chipCls(c.granted.has(tier))}>
                  <input type="checkbox" checked={c.granted.has(tier)} onChange={() => c.toggle(tier)} className="h-3.5 w-3.5" />
                  {t(`consent.scope.${tier}`, tier)}
                </label>
              ))}
            </div>
          </>
        )}

        {c.domains.length > 0 && (
          <>
            <p className="mt-3 mb-1 text-xs font-medium text-muted-foreground">{t('consent.areas_heading')}</p>
            <div className="grid grid-cols-2 gap-2">
              {c.domains.map((d) => {
                const token = domainScope(d as never);
                return (
                  <label key={d} className={chipCls(c.granted.has(token))}>
                    <input type="checkbox" checked={c.granted.has(token)} onChange={() => c.toggle(token)} className="h-3.5 w-3.5" />
                    {t(`consent.domain.${d}`, d)}
                  </label>
                );
              })}
            </div>
          </>
        )}
      </div>

      <p className="mt-4 truncate text-xs text-muted-foreground" title={c.params.resource}>
        {t('consent.resource_label')}: <span className="font-mono">{c.params.resource}</span>
      </p>

      {c.error && (
        <p className="mt-3 text-sm text-destructive">
          {c.error === 'no_scopes' ? t('consent.no_scopes') : t('consent.error')}
        </p>
      )}

      <div className="mt-5 flex justify-end gap-2">
        <button onClick={() => void c.deny()} disabled={c.submitting} className="rounded-lg border px-4 py-2.5 text-sm font-medium text-muted-foreground hover:bg-secondary hover:text-foreground disabled:opacity-50">
          {t('consent.deny')}
        </button>
        <button onClick={() => void c.approve()} disabled={c.submitting} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {c.submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {c.submitting ? t('consent.allowing') : t('consent.allow')}
        </button>
      </div>
    </Card>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-md rounded-xl border bg-background p-6 shadow-sm">{children}</div>
  );
}

function Header() {
  const { t } = useTranslation('oauth');
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-primary/10">
        <ShieldCheck className="h-5 w-5 text-primary" />
      </div>
      <div>
        <h1 className="text-base font-semibold">{t('consent.title')}</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">{t('consent.subtitle')}</p>
      </div>
    </div>
  );
}
