import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { apiJson } from '@/api';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { registerSchema, type RegisterFormValues } from '@/identity/validation/authSchemas';
import { describeApiError } from '@/lib/apiFormErrors';

export function RegisterPage() {
  const [ok, setOk] = useState('');
  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: '', password: '', display_name: '' },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    form.clearErrors('root');
    setOk('');
    try {
      const res = await apiJson<Record<string, unknown>>('/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          email: values.email,
          password: values.password,
          display_name: values.display_name?.trim() || undefined,
        }),
      });
      setOk(`Created user ${res.user_id}. You can log in.`);
    } catch (e: unknown) {
      form.setError('root', { message: describeApiError(e, 'Register failed') });
    }
  });

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Register</h2>
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
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="new-password" {...field} />
                </FormControl>
                <p className="text-sm text-muted-foreground">At least 8 characters, with a letter and a number.</p>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="display_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Display name</FormLabel>
                <FormControl>
                  <Input autoComplete="nickname" {...field} />
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
          {ok && (
            <Alert>
              <AlertTitle>Success</AlertTitle>
              <AlertDescription>{ok}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting && <Loader2 className="animate-spin" aria-hidden />}
            Register
          </Button>
        </form>
      </Form>
    </div>
  );
}
