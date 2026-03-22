import React from 'react';
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
import {
  securityPreferencesSchema,
  type SecurityPreferencesFormValues,
} from '@/identity/validation/authSchemas';
import { cn } from '@/lib/utils';
import { verifyConfirmSchema, type VerifyConfirmFormValues } from '@/identity/validation/authSchemas';
import { describeApiError } from '@/lib/apiFormErrors';

const selectClass = cn(
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
  'disabled:cursor-not-allowed disabled:opacity-50',
);

type Profile = {
  display_name?: string;
  email?: string;
  email_verified?: boolean;
};

// ── Profile sub-section ────────────────────────────────────────────────────────

function ProfileSubSection() {
  const { accessToken, refreshToken, setTokens, logoutLocal } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
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
      const p = await apiJson<Profile>('/v1/account/profile', { token: accessToken });
      setProfile(p);
      form.reset({ display_name: p.display_name || '' });
    } catch (e: unknown) {
      const er = e as Error & { status?: number };
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
      setLoadError(er.message || 'Load failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [accessToken]);

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
    <div className="space-y-4">
      <h3 className="font-medium">Profile</h3>
      {loading && <Skeleton className="h-24 w-full" />}
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
        <div className="text-sm text-muted-foreground space-y-1">
          <p>Email: <span className="text-foreground">{profile.email ?? '—'}</span>{' '}
            {profile.email_verified
              ? <span className="text-green-600 font-medium">Verified</span>
              : <span className="text-amber-600 font-medium">Not verified</span>}
          </p>
        </div>
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
          <Button type="submit" disabled={form.formState.isSubmitting || loading}>
            {form.formState.isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
            Save profile
          </Button>
        </form>
      </Form>
    </div>
  );
}

// ── Email Verification sub-section ────────────────────────────────────────────

function EmailVerificationSubSection() {
  const { accessToken } = useAuth();
  const [requestInfo, setRequestInfo] = useState('');
  const form = useForm<VerifyConfirmFormValues>({
    resolver: zodResolver(verifyConfirmSchema),
    defaultValues: { token: '' },
  });

  const request = async () => {
    form.clearErrors('root');
    setRequestInfo('');
    try {
      await apiJson('/v1/auth/verify-email/request', { method: 'POST', token: accessToken });
      setRequestInfo('Verification email sent. Check your inbox or Mailhog at http://localhost:8025.');
    } catch (e: unknown) {
      form.setError('root', { message: describeApiError(e, 'Could not send verification email') });
    }
  };

  const onSubmit = form.handleSubmit(async (values) => {
    form.clearErrors('root');
    setRequestInfo('');
    try {
      await apiJson('/v1/auth/verify-email/confirm', {
        method: 'POST',
        body: JSON.stringify({ token: values.token }),
      });
      form.setValue('token', '');
      setRequestInfo('Email verified successfully.');
    } catch (e: unknown) {
      form.setError('root', { message: describeApiError(e, 'Verification failed') });
    }
  });

  return (
    <div className="space-y-4">
      <h3 className="font-medium">Email verification</h3>
      <Button type="button" variant="secondary" onClick={() => void request()}>
        Send verification email
      </Button>
      <Form {...form}>
        <form onSubmit={onSubmit} className="space-y-4">
          <FormField
            control={form.control}
            name="token"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Verification token (from email or server log)</FormLabel>
                <FormControl>
                  <Input autoComplete="off" {...field} />
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
          {requestInfo && !form.formState.errors.root && (
            <Alert>
              <AlertTitle>Info</AlertTitle>
              <AlertDescription>{requestInfo}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
            Confirm token
          </Button>
        </form>
      </Form>
    </div>
  );
}

// ── Change Password sub-section ───────────────────────────────────────────────

type ChangePasswordFormValues = {
  current_password: string;
  new_password: string;
  confirm_new_password: string;
};

function ChangePasswordSubSection() {
  const { accessToken } = useAuth();
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [saving, setSaving] = useState(false);
  const [values, setValues] = useState<ChangePasswordFormValues>({
    current_password: '',
    new_password: '',
    confirm_new_password: '',
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSuccessMsg('');
    setErrorMsg('');
    if (!values.current_password) {
      setErrorMsg('Current password is required.');
      return;
    }
    if (values.new_password.length < 8) {
      setErrorMsg('New password must be at least 8 characters.');
      return;
    }
    if (values.new_password !== values.confirm_new_password) {
      setErrorMsg('New passwords do not match.');
      return;
    }
    if (values.new_password === values.current_password) {
      setErrorMsg('New password must differ from current password.');
      return;
    }
    setSaving(true);
    try {
      await apiJson('/v1/auth/change-password', {
        method: 'POST',
        token: accessToken,
        body: JSON.stringify({
          current_password: values.current_password,
          new_password: values.new_password,
        }),
      });
      setValues({ current_password: '', new_password: '', confirm_new_password: '' });
      setSuccessMsg('Password changed. Other sessions have been signed out.');
    } catch (e: unknown) {
      const err = e as { code?: string; message?: string };
      if (err.code === 'AUTH_INVALID_CREDENTIALS') {
        setErrorMsg('Current password is incorrect.');
      } else {
        setErrorMsg(err.message || 'Failed to change password.');
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <h3 className="font-medium">Change password</h3>
      <form onSubmit={handleSubmit} className="space-y-3 max-w-sm">
        <div className="space-y-1">
          <label className="text-sm font-medium">Current password</label>
          <Input
            type="password"
            autoComplete="current-password"
            value={values.current_password}
            onChange={(e) => setValues({ ...values, current_password: e.target.value })}
            disabled={saving}
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">New password</label>
          <Input
            type="password"
            autoComplete="new-password"
            value={values.new_password}
            onChange={(e) => setValues({ ...values, new_password: e.target.value })}
            disabled={saving}
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Confirm new password</label>
          <Input
            type="password"
            autoComplete="new-password"
            value={values.confirm_new_password}
            onChange={(e) => setValues({ ...values, confirm_new_password: e.target.value })}
            disabled={saving}
          />
        </div>
        {errorMsg && (
          <Alert variant="destructive">
            <AlertDescription>{errorMsg}</AlertDescription>
          </Alert>
        )}
        {successMsg && <p className="text-sm text-green-600">{successMsg}</p>}
        <Button type="submit" disabled={saving}>
          {saving && <Loader2 className="animate-spin" aria-hidden />}
          Change password
        </Button>
      </form>
    </div>
  );
}

// ── Security Preferences sub-section ─────────────────────────────────────────

function SecurityPrefsSubSection() {
  const { accessToken } = useAuth();
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
      form.reset({
        password_reset_method: (p.password_reset_method as 'email_link' | 'email_code') || 'email_link',
      });
    } catch (e: unknown) {
      form.setError('root', { message: (e as Error).message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [accessToken]);

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
    <div className="space-y-4">
      <h3 className="font-medium">Security preferences</h3>
      {loading && <Skeleton className="h-16 w-full" />}
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
          <Button type="submit" disabled={form.formState.isSubmitting || loading}>
            {form.formState.isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
            Save
          </Button>
        </form>
      </Form>
    </div>
  );
}

// ── AccountSection ────────────────────────────────────────────────────────────

export function AccountSection() {
  return (
    <div className="space-y-8">
      <ProfileSubSection />
      <hr />
      <EmailVerificationSubSection />
      <hr />
      <ChangePasswordSubSection />
      <hr />
      <SecurityPrefsSubSection />
    </div>
  );
}
