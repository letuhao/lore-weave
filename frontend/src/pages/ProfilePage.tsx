import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { apiJson } from '@/api';
import { useAuth } from '@/auth';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { profileSchema, type ProfileFormValues } from '@/identity/validation/authSchemas';

export function ProfilePage() {
  const { accessToken, refreshToken, setTokens, logoutLocal } = useAuth();
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [loadError, setLoadError] = useState('');
  const [msg, setMsg] = useState('');
  const [loading, setLoading] = useState(true);

  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { display_name: '' },
  });

  const load = async () => {
    setLoadError('');
    setMsg('');
    setLoading(true);
    try {
      const p = await apiJson<Record<string, unknown>>('/v1/account/profile', {
        token: accessToken,
      });
      setProfile(p);
      form.reset({ display_name: (p.display_name as string) || '' });
    } catch (e: unknown) {
      const er = e as Error & { status?: number; code?: string };
      if (er.status === 401 && refreshToken) {
        try {
          const r = await apiJson<{ access_token: string; refresh_token: string }>('/v1/auth/refresh', {
            method: 'POST',
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
          setTokens(r.access_token, r.refresh_token);
          setMsg('Session refreshed — retry profile.');
          setLoading(false);
          return;
        } catch {
          logoutLocal();
        }
      }
      setLoadError(er.message || 'load failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const onSubmit = form.handleSubmit(async (values) => {
    setMsg('');
    form.clearErrors('root');
    try {
      await apiJson('/v1/account/profile', {
        method: 'PATCH',
        token: accessToken,
        body: JSON.stringify({ display_name: values.display_name }),
      });
      setMsg('Saved.');
      await load();
    } catch (e: unknown) {
      form.setError('root', { message: (e as Error).message });
    }
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Profile</h2>
      {loading && (
        <div className="space-y-2">
          <Skeleton className="h-32 w-full" />
          <p className="text-sm text-muted-foreground">Loading…</p>
        </div>
      )}
      {loadError && (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      )}
      {msg && (
        <Alert>
          <AlertTitle>Note</AlertTitle>
          <AlertDescription>{msg}</AlertDescription>
        </Alert>
      )}
      {!loading && profile && (
        <pre className="max-h-48 overflow-auto rounded-md border bg-muted/40 p-3 text-xs">{JSON.stringify(profile, null, 2)}</pre>
      )}
      <Form {...form}>
        <form onSubmit={onSubmit} className="space-y-4">
          <FormField
            control={form.control}
            name="display_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Display name</FormLabel>
                <FormControl>
                  <Input autoComplete="nickname" disabled={loading} {...field} />
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
