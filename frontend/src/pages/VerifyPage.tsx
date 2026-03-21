import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { apiJson } from '@/api';
import { useAuth } from '@/auth';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { verifyConfirmSchema, type VerifyConfirmFormValues } from '@/identity/validation/authSchemas';
import { describeApiError } from '@/lib/apiFormErrors';

export function VerifyPage() {
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
      await apiJson('/v1/auth/verify-email/request', {
        method: 'POST',
        token: accessToken,
      });
      setRequestInfo(
        'Verification email sent (if SMTP is configured). Check Mailhog at http://localhost:8025 or the auth-service logs for the token.',
      );
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
      setRequestInfo('Email verified.');
    } catch (e: unknown) {
      form.setError('root', { message: describeApiError(e, 'Verification failed') });
    }
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Email verification</h2>
      <Button type="button" variant="secondary" className="w-full" onClick={() => void request()}>
        Request verification email
      </Button>
      <Form {...form}>
        <form onSubmit={onSubmit} className="space-y-4">
          <FormField
            control={form.control}
            name="token"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Token (from email or server log)</FormLabel>
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
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
            Confirm
          </Button>
        </form>
      </Form>
    </div>
  );
}
