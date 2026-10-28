import i18n from '@/i18n';
import { UI_LOCALES } from '@/lib/languages';
import { loadPrefFromServer, savePrefToServer } from '@/lib/syncPrefs';

/**
 * Server-side persistence for the UI language.
 *
 * The i18next detector keeps the choice in localStorage (`lw_language`), which
 * is lost on a cleared browser / another device — and with it the whole
 * localization ("полностью пропала русская локализация", 2026-10-25). The
 * account preference `ui_language` in auth-service's user_preferences is the
 * durable copy: applied at app bootstrap (overriding the device default —
 * the server is the source of truth for a logged-in user), written on every
 * change. localStorage stays the fast path and the logged-out store.
 */

/** The stored code is a registry UI locale (base-code match: ru-RU → ru). */
function isSupported(code: string): boolean {
  return UI_LOCALES.some((l) => code === l || code.startsWith(`${l}-`));
}

/** Applies the current i18n language to the account, fire-and-forget. */
export function persistUiLanguage(token: string | null | undefined): void {
  const code = i18n.language;
  if (!code) return;
  void savePrefToServer('ui_language', code, token);
}

/**
 * Applies the account's stored `ui_language` (if any) on bootstrap. Runs once
 * per token; safe to call from a top-level effect after auth resolves.
 */
let appliedForToken: string | null = null;
export async function applyAccountLanguage(token: string | null | undefined): Promise<void> {
  if (!token || appliedForToken === token) return;
  appliedForToken = token;
  const stored = await loadPrefFromServer<string>('ui_language', token);
  if (!stored || !isSupported(stored)) return;
  // Base-code compare: 'ru' should not re-apply over the equivalent 'ru-RU'.
  const current = i18n.language;
  const sameLanguage = current === stored || current.startsWith(`${stored}-`);
  if (!sameLanguage && i18n.language !== stored) {
    await i18n.changeLanguage(stored);
  }
}
