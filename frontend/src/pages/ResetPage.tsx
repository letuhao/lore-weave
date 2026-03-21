import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { apiJson } from '@/api';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { resetSchema, type ResetFormValues } from '@/identity/validation/authSchemas';
import { describeApiError } from '@/lib/apiFormErrors';

export function ResetPage() {
  const [ok, setOk] = useState('');
  const form = useForm<ResetFormValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { token: '', new_password: '' },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    form.clearErrors('root');
    setOk('');
    try {
      await apiJson('/v1/auth/password-reset/confirm', {
        method: 'POST',
        body: JSON.stringify({ token: values.token, new_password: values.new_password }),
      });
      setOk('Password updated — log in again.');
    } catch (e: unknown) {
      form.setError('root', { message: describeApiError(e, 'Reset failed') });
    }
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Reset password</h2>
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
          <FormField
            control={form.control}
            name="new_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>New password</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="new-password" {...field} />
                </FormControl>
                <p className="text-sm text-muted-foreground">At least 8 characters, with a letter and a number.</p>
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
          {ok && (
            <Alert>
              <AlertTitle>Success</AlertTitle>
              <AlertDescription>{ok}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
            Confirm reset
          </Button>
        </form>
      </Form>
    </div>
  );
}
