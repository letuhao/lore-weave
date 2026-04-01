import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2, CheckCircle } from 'lucide-react';
import { apiJson } from '@/api';
import { AuthCard } from './AuthCard';

export function ResetPage() {
  const { t } = useTranslation('auth');
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const schema = z.object({
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
      await apiJson('/v1/auth/password-reset/confirm', {
        method: 'POST',
        body: JSON.stringify({ token, new_password: data.password }),
      });
      setDone(true);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <AuthCard
      title={t('reset.title')}
      subtitle={t('reset.subtitle')}
    >
      {done ? (
        <div className="flex flex-col items-center gap-3 py-4">
          <CheckCircle className="h-10 w-10 text-success" />
          <p className="text-sm text-muted-foreground">{t('reset.success')}</p>
          <Link to="/login" className="text-sm text-primary hover:underline">{t('reset.sign_in')}</Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('reset.password')}</label>
            <input
              {...register('password')}
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              className="w-full rounded-md border bg-card px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
            {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('reset.confirm')}</label>
            <input
              {...register('confirmPassword')}
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              className="w-full rounded-md border bg-card px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
            {errors.confirmPassword && <p className="text-xs text-destructive">{errors.confirmPassword.message}</p>}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('reset.submit')}
          </button>
        </form>
      )}
    </AuthCard>
  );
}
