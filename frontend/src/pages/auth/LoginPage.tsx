import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/auth';
import { apiJson } from '@/api';
import { AuthCard } from './AuthCard';

export function LoginPage() {
  const { t } = useTranslation('auth');
  const { setTokens } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState('');

  // Where to go after login — saved by RequireAuth, or default to /books
  const from = (location.state as { from?: string })?.from || '/books';

  const schema = z.object({
    email: z.string().min(1, t('validation.email_required')).email(t('validation.email_invalid')),
    password: z.string().min(1, t('validation.password_required')),
  });

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: z.infer<typeof schema>) => {
    setError('');
    try {
      const res = await apiJson<{ access_token: string; refresh_token: string }>('/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      setTokens(res.access_token, res.refresh_token);
      navigate(from, { replace: true });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <AuthCard
      title={t('login.title')}
      subtitle={t('login.subtitle')}
      footer={
        <span>
          {t('login.no_account')}{' '}
          <Link to="/register" className="text-primary hover:underline">{t('login.sign_up')}</Link>
        </span>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {error && (
          <div
            data-testid="auth-error-message"
            className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </div>
        )}

        <div className="space-y-1.5">
          <label className="text-sm font-medium">{t('login.email')}</label>
          <input
            {...register('email')}
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            data-testid="auth-email-input"
            className="w-full rounded-md border bg-card px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
          {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">{t('login.password')}</label>
            <Link to="/forgot" className="text-xs text-muted-foreground transition-colors hover:text-foreground">
              {t('login.forgot')}
            </Link>
          </div>
          <input
            {...register('password')}
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            data-testid="auth-password-input"
            className="w-full rounded-md border bg-card px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
          {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          data-testid="auth-submit-button"
          className="flex w-full items-center justify-center gap-2 rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {t('login.submit')}
        </button>
      </form>
    </AuthCard>
  );
}
