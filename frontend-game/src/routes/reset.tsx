// Password recovery. View only — logic lives in `usePasswordReset`.
//
// Reached two ways: from the login screen's "forgot password" link, or straight
// from the emailed deep link `/reset?token=…` (auth-service builds that URL from
// PUBLIC_APP_URL). Both land here; the token decides which phase shows first.

import { useSearchParams, Link } from 'react-router-dom';
import { Button } from '@/components/shared/Button';
import { usePasswordReset } from '@/hooks/use-password-reset';
import { useTranslation } from 'react-i18next';
import type { JSX } from 'react';

const field =
  'w-full px-3 py-2 rounded bg-slate-800 border border-slate-600 text-slate-100 ' +
  'placeholder:text-slate-500 focus:outline-none focus:border-indigo-500';

export function ResetRoute(): JSX.Element {
  const { t } = useTranslation('auth');
  const [params] = useSearchParams();
  const r = usePasswordReset(params.get('token') ?? '');

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-slate-100 px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-bold mb-1">{t('reset_title')}</h1>

        {r.phase === 'request' && (
          <>
            <p className="text-slate-400 text-sm mb-5">{t('reset_request_intro')}</p>
            <form
              className="flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (r.canSend) void r.sendLink();
              }}
            >
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">{t('email')}</span>
                <input
                  className={field}
                  type="email"
                  value={r.email}
                  onChange={(e) => r.setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </label>
              {r.errorKey && (
                <p role="alert" className="text-sm text-rose-400">
                  {t(r.errorKey)}
                </p>
              )}
              <Button type="submit" disabled={!r.canSend} className="disabled:opacity-50">
                {r.pending ? '…' : t('reset_send')}
              </Button>
            </form>
            <button
              type="button"
              onClick={r.goToConfirm}
              className="mt-4 text-xs underline text-indigo-400"
            >
              {t('reset_have_token')}
            </button>
          </>
        )}

        {r.phase === 'sent' && (
          <>
            {/* Same message regardless of whether the account exists. */}
            <p role="status" className="text-sm text-slate-300 leading-relaxed mb-5">
              {t('reset_sent', { email: r.email })}
            </p>
            <Button onClick={r.goToConfirm}>{t('reset_have_token')}</Button>
          </>
        )}

        {r.phase === 'confirm' && (
          <>
            <p className="text-slate-400 text-sm mb-5">{t('password_hint')}</p>
            <form
              className="flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (r.canSubmit) void r.submitNewPassword();
              }}
            >
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">{t('reset_token')}</span>
                <input
                  className={`${field} font-mono text-xs`}
                  value={r.token}
                  onChange={(e) => r.setToken(e.target.value)}
                  required
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">{t('reset_new_password')}</span>
                <input
                  className={field}
                  type="password"
                  value={r.password}
                  onChange={(e) => r.setPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">{t('confirm_password')}</span>
                <input
                  className={field}
                  type="password"
                  value={r.confirmPassword}
                  onChange={(e) => r.setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </label>
              {r.errorKey && (
                <p role="alert" className="text-sm text-rose-400">
                  {t(r.errorKey)}
                </p>
              )}
              <Button type="submit" disabled={!r.canSubmit} className="disabled:opacity-50">
                {r.pending ? '…' : t('reset_submit')}
              </Button>
            </form>
          </>
        )}

        {r.phase === 'done' && (
          <p role="status" className="text-sm text-emerald-400 leading-relaxed mb-5">
            {t('reset_done')}
          </p>
        )}

        <p className="mt-6 text-xs">
          <Link to="/login" className="underline text-indigo-400">
            {t('back_to_sign_in')}
          </Link>
        </p>
      </div>
    </div>
  );
}
