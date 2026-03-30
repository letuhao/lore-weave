import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/auth';
import { apiJson } from '@/api';
import { AuthCard } from './AuthCard';

export function RegisterPage() {
  const { t } = useTranslation('auth');
  const { setTokens } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState('');

  const schema = z.object({
    email: z.string().min(1, t('validation.email_required')).email(t('validation.email_invalid')),
    password: z.string().min(8, t('validation.password_min')),
    confirmPassword: z.string().min(1, t('validation.password_required')),
  }).refine((d) => d.password === d.confirmPassword, {
    message: t('validation.password_mismatch'),
    path: ['confirmPassword'],
  });

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: z.infer<typeof schema>) => {
    setError('');
    try {
      const res = await apiJson<{ access_token: string; refresh_token: string }>('/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email: data.email, password: data.password }),
      });
      setTokens(res.access_token, res.refresh_token);
      navigate('/books');
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <AuthCard
      title={t('register.title')}
      subtitle={t('register.subtitle')}
      footer={
        <span>
          {t('register.has_account')}{' '}
          <Link to="/login" className="text-primary hover:underline">{t('register.sign_in')}</Link>
        </span>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <div className="space-y-1.5">
          <label className="text-sm font-medium">{t('register.email')}</label>
          <input
            {...register('email')}
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
          {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium">{t('register.password')}</label>
          <input
            {...register('password')}
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
          {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium">{t('register.confirm')}</label>
          <input
            {...register('confirmPassword')}
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
          {errors.confirmPassword && <p className="text-xs text-destructive">{errors.confirmPassword.message}</p>}
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {t('register.submit')}
        </button>
      </form>
    </AuthCard>
  );
}
