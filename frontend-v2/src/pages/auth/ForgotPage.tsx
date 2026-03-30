import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2, CheckCircle } from 'lucide-react';
import { apiJson } from '@/api';
import { AuthCard } from './AuthCard';

export function ForgotPage() {
  const { t } = useTranslation('auth');
  const [error, setError] = useState('');
  const [sent, setSent] = useState(false);

  const schema = z.object({
    email: z.string().min(1, t('validation.email_required')).email(t('validation.email_invalid')),
  });

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: z.infer<typeof schema>) => {
    setError('');
    try {
      await apiJson('/v1/auth/password-reset/request', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      setSent(true);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <AuthCard
      title={t('forgot.title')}
      subtitle={t('forgot.subtitle')}
      footer={
        <Link to="/login" className="text-primary hover:underline">{t('forgot.back')}</Link>
      }
    >
      {sent ? (
        <div className="flex flex-col items-center gap-3 py-4">
          <CheckCircle className="h-10 w-10 text-success" />
          <p className="text-sm text-muted-foreground">{t('forgot.sent')}</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('forgot.email')}</label>
            <input
              {...register('email')}
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
            {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('forgot.submit')}
          </button>
        </form>
      )}
    </AuthCard>
  );
}
