import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle, Loader2 } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiJson } from '@/api';
import { AuthCard } from './AuthCard';

type VerifyState = 'idle' | 'submitting' | 'success';

export function VerifyPage() {
  const { t } = useTranslation('auth');
  const [searchParams] = useSearchParams();
  const queryToken = searchParams.get('token') ?? '';
  const [token, setToken] = useState(queryToken);
  const [error, setError] = useState('');
  const [state, setState] = useState<VerifyState>('idle');
  const autoSubmittedToken = useRef<string | null>(null);

  const verify = useCallback(async (candidate: string) => {
    const value = candidate.trim();
    if (!value) {
      setError(t('verify.token_required', { defaultValue: 'Enter the verification token.' }));
      return;
    }

    setError('');
    setState('submitting');
    try {
      await apiJson('/v1/auth/verify-email/confirm', {
        method: 'POST',
        body: JSON.stringify({ token: value }),
      });
      setState('success');
    } catch (err) {
      setState('idle');
      setError((err as Error).message || t('verify.invalid', {
        defaultValue: 'This verification token is invalid or has expired.',
      }));
    }
  }, [t]);

  // Email links already contain the token. Confirm once automatically so the normal
  // one-click flow works, while keeping the form available for clients that strip query strings.
  useEffect(() => {
    if (!queryToken || autoSubmittedToken.current === queryToken) return;
    autoSubmittedToken.current = queryToken;
    void verify(queryToken);
  }, [queryToken, verify]);

  return (
    <AuthCard
      title={t('verify.title', { defaultValue: 'Verify your email' })}
      subtitle={t('verify.subtitle', {
        defaultValue: 'Confirm your email address to finish setting up your account.',
      })}
      footer={(
        <span>
          {t('verify.have_account', { defaultValue: 'Already verified?' })}{' '}
          <Link to="/login" className="text-primary hover:underline">
            {t('verify.sign_in', { defaultValue: 'Sign in' })}
          </Link>
        </span>
      )}
    >
      {state === 'success' ? (
        <div className="flex flex-col items-center gap-3 py-4" data-testid="verify-success">
          <CheckCircle className="h-10 w-10 text-success" />
          <p className="text-center text-sm text-muted-foreground">
            {t('verify.success', { defaultValue: 'Your email has been verified successfully.' })}
          </p>
          <Link to="/login" className="text-sm text-primary hover:underline">
            {t('verify.sign_in', { defaultValue: 'Sign in' })}
          </Link>
        </div>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void verify(token);
          }}
          className="space-y-4"
        >
          {error && (
            <div
              data-testid="verify-error"
              role="alert"
              className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label htmlFor="verification-token" className="text-sm font-medium">
              {t('verify.token', { defaultValue: 'Verification token' })}
            </label>
            <input
              id="verification-token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              autoComplete="one-time-code"
              spellCheck={false}
              data-testid="verify-token-input"
              className="w-full rounded-md border bg-card px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
              placeholder={t('verify.token_placeholder', { defaultValue: 'Paste the token from your email' })}
            />
          </div>

          <button
            type="submit"
            disabled={state === 'submitting'}
            data-testid="verify-submit-button"
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {state === 'submitting' && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('verify.submit', { defaultValue: 'Verify email' })}
          </button>
        </form>
      )}
    </AuthCard>
  );
}
