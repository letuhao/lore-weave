import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { apiJson } from '@/api';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { forgotSchema, type ForgotFormValues } from '@/identity/validation/authSchemas';

export function ForgotPage() {
  const [info, setInfo] = useState('');
  const form = useForm<ForgotFormValues>({
    resolver: zodResolver(forgotSchema),
    defaultValues: { email: '' },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setInfo('');
    try {
      await apiJson('/v1/auth/password-reset/request', {
        method: 'POST',
        body: JSON.stringify({ email: values.email }),
      });
      setInfo(
        'If the account exists, a reset was triggered. Check Mailhog at http://localhost:8025 or auth-service logs for the token.',
      );
    } catch {
      setInfo('Request accepted.');
    }
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Forgot password</h2>
      <Form {...form}>
        <form onSubmit={onSubmit} className="space-y-4">
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input type="email" autoComplete="email" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          {info && (
            <Alert>
              <AlertTitle>Note</AlertTitle>
              <AlertDescription>{info}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
            Request reset
          </Button>
        </form>
      </Form>
    </div>
  );
}
