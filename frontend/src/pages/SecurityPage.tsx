import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { apiJson } from '@/api';
import { useAuth } from '@/auth';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Skeleton } from '@/components/ui/skeleton';
import {
  securityPreferencesSchema,
  type SecurityPreferencesFormValues,
} from '@/identity/validation/authSchemas';
import { cn } from '@/lib/utils';

const selectClass = cn(
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
  'disabled:cursor-not-allowed disabled:opacity-50',
);

export function SecurityPage() {
  const { accessToken } = useAuth();
  const [prefs, setPrefs] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  const form = useForm<SecurityPreferencesFormValues>({
    resolver: zodResolver(securityPreferencesSchema),
    defaultValues: { password_reset_method: 'email_link' },
  });

  const load = async () => {
    setLoading(true);
    form.clearErrors('root');
    try {
      const p = await apiJson<Record<string, unknown>>('/v1/account/security/preferences', {
        token: accessToken,
      });
      setPrefs(p);
      form.reset({
        password_reset_method: (p.password_reset_method as 'email_link' | 'email_code') || 'email_link',
      });
    } catch (e: unknown) {
      form.setError('root', { message: (e as Error).message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const onSubmit = form.handleSubmit(async (values) => {
    form.clearErrors('root');
    try {
      await apiJson('/v1/account/security/preferences', {
        method: 'PATCH',
        token: accessToken,
        body: JSON.stringify({ password_reset_method: values.password_reset_method }),
      });
      await load();
    } catch (e: unknown) {
      form.setError('root', { message: (e as Error).message });
    }
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Security preferences</h2>
      {loading && (
        <div className="space-y-2">
          <Skeleton className="h-24 w-full" />
          <p className="text-sm text-muted-foreground">Loading…</p>
        </div>
      )}
      {!loading && prefs && (
        <pre className="max-h-40 overflow-auto rounded-md border bg-muted/40 p-3 text-xs">{JSON.stringify(prefs, null, 2)}</pre>
      )}
      <Form {...form}>
        <form onSubmit={onSubmit} className="space-y-4">
          <FormField
            control={form.control}
            name="password_reset_method"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password reset method</FormLabel>
                <FormControl>
                  <select className={selectClass} {...field}>
                    <option value="email_link">email_link</option>
                    <option value="email_code">email_code</option>
                  </select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          {form.formState.errors.root && (
            <Alert variant="destructive">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{form.formState.errors.root.message}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting || loading}>
            {form.formState.isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
            Save
          </Button>
        </form>
      </Form>
    </div>
  );
}
