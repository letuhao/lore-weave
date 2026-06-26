// W6 §3.4 — the anti-repetition warning (the cowrite craft-nudge made structural,
// §11). Announced via aria-live so a screen-reader user hears it (§5.1). Not an
// error — an advisory. Render-only.
import { useTranslation } from 'react-i18next';
import type { OveruseWarning } from '../types';

export function OveruseBanner({ warning }: { warning: OveruseWarning }) {
  const { t } = useTranslation('composition');
  return (
    <div
      data-testid="motif-overuse"
      role="status"
      aria-live="polite"
      className="rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200"
    >
      ⚠ {t('motif.overuse', {
        name: warning.motif_name, chapters: warning.applied_in.join(', '),
        defaultValue: '"{{name}}" is already used in {{chapters}} — consider varying it.',
      })}
    </div>
  );
}
