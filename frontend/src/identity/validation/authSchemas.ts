import * as z from 'zod';

/** Mirrors auth-service `validEmail` (internal/api/util.go). */
const EMAIL_PATTERN = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/;

const PASSWORD_MIN_LENGTH = 8;

/** Mirrors Go `validPassword`: min length, at least one letter and one decimal digit. */
export function passwordMeetsPolicy(pw: string, minLen = PASSWORD_MIN_LENGTH): boolean {
  if (pw.length < minLen) return false;
  let letter = false;
  let digit = false;
  for (const ch of pw) {
    if (/\p{L}/u.test(ch)) letter = true;
    if (/\d/.test(ch)) digit = true;
  }
  return letter && digit;
}

const emailField = z
  .string()
  .trim()
  .min(1, 'Email is required')
  .refine((s) => EMAIL_PATTERN.test(s), 'Enter a valid email address');

const registerPasswordField = z
  .string()
  .min(1, 'Password is required')
  .refine(
    (s) => passwordMeetsPolicy(s),
    `Password must be at least ${PASSWORD_MIN_LENGTH} characters and include a letter and a number`,
  );

const resetPasswordField = z
  .string()
  .min(1, 'New password is required')
  .refine(
    (s) => passwordMeetsPolicy(s),
    `Password must be at least ${PASSWORD_MIN_LENGTH} characters and include a letter and a number`,
  );

export const loginSchema = z.object({
  email: emailField,
  password: z.string().min(1, 'Password is required'),
});

export const registerSchema = z.object({
  email: emailField,
  password: registerPasswordField,
  display_name: z.string().optional(),
});

export const forgotSchema = z.object({
  email: emailField,
});

export const resetSchema = z.object({
  token: z.string().min(1, 'Token is required'),
  new_password: resetPasswordField,
});

export const verifyConfirmSchema = z.object({
  token: z.string().min(1, 'Token is required'),
});

export const profileSchema = z.object({
  display_name: z.string(),
});

export const securityPreferencesSchema = z.object({
  password_reset_method: z.enum(['email_link', 'email_code']),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
export type RegisterFormValues = z.infer<typeof registerSchema>;
export type ForgotFormValues = z.infer<typeof forgotSchema>;
export type ResetFormValues = z.infer<typeof resetSchema>;
export type VerifyConfirmFormValues = z.infer<typeof verifyConfirmSchema>;
export type ProfileFormValues = z.infer<typeof profileSchema>;
export type SecurityPreferencesFormValues = z.infer<typeof securityPreferencesSchema>;
