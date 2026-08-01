// Login / register screen. View only — all logic lives in `useAuthForm`.
//
// One account, two apps: this signs in against the same `auth-service` and the
// same `users` table the novel-workflow app uses, so an existing LoreWeave
// account works here with no migration and no second registration.

import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Button } from '@/components/shared/Button';
import { LanguageSwitcher } from '@/components/shared/LanguageSwitcher';
import { useAuthForm } from '@/hooks/use-auth-form';
import type { JSX } from 'react';

const field =
  'w-full px-3 py-2 rounded bg-slate-800 border border-slate-600 text-slate-100 ' +
  'placeholder:text-slate-500 focus:outline-none focus:border-indigo-500';

export function LoginRoute(): JSX.Element {
  const { t } = useTranslation('auth');
  const navigate = useNavigate();
  const location = useLocation();
  // Preserve the destination a guard redirected away from, so a deep link
  // survives the login round-trip instead of dumping everyone on the default.
  const from = (location.state as { from?: string } | null)?.from ?? '/world-select';
  const f = useAuthForm(() => navigate(from, { replace: true }));

  const isRegister = f.mode === 'register';

  // Post-registration hand-off. Deliberately NOT a wall: the account works
  // unverified (auth-service issues tokens either way), so this informs and
  // gets out of the way rather than gating play behind an inbox round-trip.
  if (f.registeredEmail) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-slate-100 px-4">
        <div className="w-full max-w-sm">
          <h1 className="text-2xl font-bold mb-3">LoreWeave</h1>
          <p role="status" className="text-sm text-slate-300 leading-relaxed mb-5">
            {t('check_inbox', { email: f.registeredEmail })}
          </p>
          <Button onClick={f.dismissNotice}>{t('common:next')}</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-slate-100 px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-start justify-between mb-1">
          <h1 className="text-3xl font-bold">LoreWeave</h1>
          <LanguageSwitcher />
        </div>
        <p className="text-slate-400 text-sm mb-6">
          {isRegister ? t('create_account_title') : t('sign_in_title')}
        </p>

        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (f.canSubmit) void f.submit();
          }}
        >
          {isRegister && (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{t('display_name')}</span>
              <input
                className={field}
                value={f.displayName}
                onChange={(e) => f.setDisplayName(e.target.value)}
                autoComplete="nickname"
              />
            </label>
          )}

          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">{t('email')}</span>
            <input
              className={field}
              type="email"
              value={f.email}
              onChange={(e) => f.setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">{t('password')}</span>
            <input
              className={field}
              type="password"
              value={f.password}
              onChange={(e) => f.setPassword(e.target.value)}
              autoComplete={isRegister ? 'new-password' : 'current-password'}
              required
            />
            {isRegister && <span className="text-xs text-slate-500">{t('password_hint')}</span>}
          </label>

          {isRegister && (
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{t('confirm_password')}</span>
              <input
                className={field}
                type="password"
                value={f.confirmPassword}
                onChange={(e) => f.setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </label>
          )}

          {f.errorKey && (
            <p role="alert" className="text-sm text-rose-400">
              {t(f.errorKey)}
              {f.suggestLogin && (
                <button
                  type="button"
                  onClick={() => f.setMode('login')}
                  className="ml-2 underline text-indigo-400"
                >
                  {t('sign_in')}
                </button>
              )}
            </p>
          )}

          <Button type="submit" disabled={!f.canSubmit} className="mt-1 disabled:opacity-50">
            {f.pending ? '…' : isRegister ? t('create_account') : t('sign_in')}
          </Button>
        </form>

        <p className="text-sm text-slate-400 mt-5">
          {isRegister ? t('have_account') : t('no_account')}{' '}
          <button
            type="button"
            className="underline text-indigo-400"
            onClick={() => f.setMode(isRegister ? 'login' : 'register')}
          >
            {isRegister ? t('sign_in') : t('sign_up')}
          </button>
        </p>

        {!isRegister && (
          <p className="mt-3 text-xs">
            <Link to="/reset" className="underline text-indigo-400">
              {t('forgot_password')}
            </Link>
          </p>
        )}

        <p className="text-xs text-slate-500 mt-6 leading-relaxed">{t('shared_account')}</p>
      </div>
    </div>
  );
}
