// Controller for the login / register form. Owns all logic + state; the route
// component renders and does nothing else (CLAUDE.md React-MVC rule).

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AuthError, checkPassword, login, register } from '@loreweave/auth-client';
import { useSession } from '@/store/session-context';

export type AuthMode = 'login' | 'register';

interface AuthFormState {
  mode: AuthMode;
  email: string;
  password: string;
  confirmPassword: string;
  displayName: string;
  pending: boolean;
  /**
   * i18n KEY of the failure, not a rendered sentence. The hook is the
   * controller and must stay language-free; the view translates. Returning a
   * localised string here would bake English/Vietnamese into logic and make
   * the copy invisible to the locale-parity test.
   */
  errorKey: string | null;
  /** Set when the failure really means "this account exists, just sign in". */
  suggestLogin: boolean;
  /**
   * Set after a successful registration when the server sent a verification
   * mail (`verification_required`). The account WORKS unverified — login issues
   * tokens either way, verified live against auth-service — so this is an
   * informational hand-off, never a wall.
   */
  registeredEmail: string | null;
}

const INITIAL: AuthFormState = {
  mode: 'login',
  email: '',
  password: '',
  confirmPassword: '',
  displayName: '',
  pending: false,
  errorKey: null,
  suggestLogin: false,
  registeredEmail: null,
};

/**
 * Map an auth-service error code to something a player can act on.
 *
 * `AUTH_EMAIL_ALREADY_EXISTS` is the interesting one, and the reason this
 * mapping is not generic: both apps share one account store, so a novel-app
 * user hitting Register here is not making a mistake — they already HAVE a
 * LoreWeave account. A red "email already registered" would be technically
 * true and completely unhelpful. Tell them to sign in instead.
 */
function describe(err: unknown): { errorKey: string; suggestLogin: boolean } {
  if (err instanceof AuthError) {
    switch (err.code) {
      case 'AUTH_INVALID_CREDENTIALS':
        return { errorKey: 'error.invalid_credentials', suggestLogin: false };
      case 'AUTH_EMAIL_ALREADY_EXISTS':
        return { errorKey: 'error.email_exists', suggestLogin: true };
      case 'AUTH_VALIDATION_ERROR':
        return { errorKey: 'error.validation', suggestLogin: false };
      default:
        return { errorKey: 'error.network', suggestLogin: false };
    }
  }
  // A network failure never reaches the service, so it carries no code. Naming
  // the likely cause beats "Failed to fetch" — in dev this is almost always
  // the gateway being down behind the vite /v1 proxy.
  return { errorKey: 'error.network', suggestLogin: false };
}

const PROBLEM_KEY = {
  too_short: 'error.password_too_short',
  needs_letter: 'error.password_needs_letter',
  needs_digit: 'error.password_needs_digit',
} as const;

export function useAuthForm(onSuccess: () => void) {
  const [state, setState] = useState<AuthFormState>(INITIAL);
  const { syncFromStorage } = useSession();
  const { i18n } = useTranslation();

  const patch = useCallback((p: Partial<AuthFormState>) => setState((s) => ({ ...s, ...p })), []);

  const setMode = useCallback(
    (mode: AuthMode) => patch({ mode, errorKey: null, suggestLogin: false }),
    [patch],
  );

  const submit = useCallback(async () => {
    const { mode, email, password, confirmPassword, displayName } = state;

    // Validate BEFORE the round-trip. The server enforces the same policy, but
    // its 400 is a single opaque "invalid email or password policy" that names
    // neither which field nor which rule — leaving the user to guess.
    if (mode === 'register') {
      if (password !== confirmPassword) {
        patch({ errorKey: 'error.password_mismatch', suggestLogin: false });
        return;
      }
      const problems = checkPassword(password);
      if (problems.length > 0) {
        patch({ errorKey: PROBLEM_KEY[problems[0]!], suggestLogin: false });
        return;
      }
    }

    patch({ pending: true, errorKey: null, suggestLogin: false });
    try {
      if (mode === 'register') {
        const created = await register({
          email: email.trim(),
          password,
          display_name: displayName.trim() || undefined,
          // The app already knows the user's language — dropping it here left
          // every game-registered account with a null locale server-side, so
          // anything reading it (mail, notifications) fell back to English.
          locale: i18n.language,
        });
        // register() issues NO tokens (handlers.go returns a profile only), so
        // a sign-in MUST follow or the user lands on a still-logged-out app.
        await login(email.trim(), password);
        syncFromStorage();
        if (created.verification_required) {
          // Tell them a mail is waiting, then let them in on their own click.
          patch({ pending: false, registeredEmail: created.email });
          return;
        }
        onSuccess();
        return;
      }

      await login(email.trim(), password);
      // login() wrote storage, and `storage` events do not fire in the writing
      // tab — reflect it into React state here.
      syncFromStorage();
      onSuccess();
    } catch (err) {
      const { errorKey, suggestLogin } = describe(err);
      patch({ pending: false, errorKey, suggestLogin });
    }
  }, [state, patch, syncFromStorage, onSuccess, i18n.language]);

  return {
    ...state,
    setMode,
    setEmail: (email: string) => patch({ email }),
    setPassword: (password: string) => patch({ password }),
    setConfirmPassword: (confirmPassword: string) => patch({ confirmPassword }),
    setDisplayName: (displayName: string) => patch({ displayName }),
    submit,
    /** Continue into the game after the post-registration notice. */
    dismissNotice: onSuccess,
    canSubmit: state.email.trim().length > 0 && state.password.length > 0 && !state.pending,
  };
}
