// Part B — the OPT-IN "Set up this book" secondary shown under a work-gated door. Owns its own
// readiness + setup hooks so the door stays presentational. Renders NOTHING once the book already has
// a plan (the narrow Work door alone suffices then) — so it only appears when it adds value: the book
// has neither, and one click can light up every Story-Bible surface at once.
import { useTranslation } from 'react-i18next';
import { useBookReadiness } from '../hooks/useBookReadiness';
import { useBookSetup } from '../hooks/useBookSetup';

export function SetupEverythingLink({ bookId, token }: { bookId: string; token: string | null }) {
  const { t } = useTranslation('studio');
  const { hasPlan, loading } = useBookReadiness(bookId);
  const { setUp, busy } = useBookSetup(bookId, token);

  // Only offer the shortcut when the book has NO plan yet — otherwise the Work door alone is enough.
  if (loading || hasPlan || !setUp) return null;

  return (
    <button
      type="button"
      data-testid="book-setup-everything"
      onClick={setUp}
      disabled={busy}
      className="text-[11px] text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
    >
      {busy
        ? t('setup.everythingBusy', { defaultValue: 'Setting up…' })
        : t('setup.everything', { defaultValue: 'Or set up this book completely' })}
    </button>
  );
}
