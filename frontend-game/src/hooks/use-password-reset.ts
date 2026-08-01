// Controller for the password-recovery flow. Two phases, one screen.
//
// Phase is driven by whether a token is in hand, not by a wizard step: arriving
// from the emailed link (`/reset?token=…`) lands straight in `confirm`, while a
// user who clicked "forgot password" starts at `request`. Both paths converge.

import { useCallback, useState } from 'react';
import { AuthError, checkPassword, confirmPasswordReset, requestPasswordReset } from '@loreweave/auth-client';

export type ResetPhase = 'request' | 'sent' | 'confirm' | 'done';

interface State {
  phase: ResetPhase;
  email: string;
  token: string;
  password: string;
  confirmPassword: string;
  pending: boolean;
  errorKey: string | null;
}

const PROBLEM_KEY = {
  too_short: 'error.password_too_short',
  needs_letter: 'error.password_needs_letter',
  needs_digit: 'error.password_needs_digit',
} as const;

export function usePasswordReset(initialToken: string) {
  const [s, setS] = useState<State>({
    // A token in the URL means the user came from the mail — skip straight to
    // choosing a new password rather than asking for their email again.
    phase: initialToken ? 'confirm' : 'request',
    email: '',
    token: initialToken,
    password: '',
    confirmPassword: '',
    pending: false,
    errorKey: null,
  });

  const patch = useCallback((p: Partial<State>) => setS((prev) => ({ ...prev, ...p })), []);

  const sendLink = useCallback(async () => {
    patch({ pending: true, errorKey: null });
    try {
      await requestPasswordReset(s.email);
      // Deliberately the same outcome whether or not the account exists — the
      // server answers 202 either way to avoid an enumeration oracle, and the
      // UI must not leak what the API refused to.
      patch({ pending: false, phase: 'sent' });
    } catch {
      patch({ pending: false, errorKey: 'error.network' });
    }
  }, [s.email, patch]);

  const submitNewPassword = useCallback(async () => {
    if (s.password !== s.confirmPassword) {
      patch({ errorKey: 'error.password_mismatch' });
      return;
    }
    // Check policy BEFORE sending: the server answers AUTH_RESET_TOKEN_INVALID
    // for a weak password too, so an unchecked submit tells the user their link
    // expired when the real problem is the password they just typed.
    const problems = checkPassword(s.password);
    if (problems.length > 0) {
      patch({ errorKey: PROBLEM_KEY[problems[0]!] });
      return;
    }
    patch({ pending: true, errorKey: null });
    try {
      await confirmPasswordReset(s.token, s.password);
      patch({ pending: false, phase: 'done' });
    } catch (err) {
      const key =
        err instanceof AuthError && err.code === 'AUTH_RESET_TOKEN_INVALID'
          ? 'error.reset_token_invalid'
          : 'error.network';
      patch({ pending: false, errorKey: key });
    }
  }, [s.password, s.confirmPassword, s.token, patch]);

  return {
    ...s,
    setEmail: (email: string) => patch({ email }),
    setToken: (token: string) => patch({ token }),
    setPassword: (password: string) => patch({ password }),
    setConfirmPassword: (confirmPassword: string) => patch({ confirmPassword }),
    goToConfirm: () => patch({ phase: 'confirm', errorKey: null }),
    sendLink,
    submitNewPassword,
    canSend: s.email.trim().length > 0 && !s.pending,
    canSubmit: s.token.trim().length > 0 && s.password.length > 0 && !s.pending,
  };
}
