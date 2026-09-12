// W6 §4.2 — the load-bearing first-run empty library state. A fresh user has the
// system seed motifs visible but ZERO user motifs; this must NOT read as "broken".
// It reassures the seeds are there, offers the TWO doors (manual + planner auto-
// bind), uses plain language (no Greimas/Propp), and is NEVER a dead end.
import { useTranslation } from 'react-i18next';

type Props = {
  onNewMotif: () => void;
  onBrowseSystem: () => void;
};

export function MotifEmptyState({ onNewMotif, onBrowseSystem }: Props) {
  const { t } = useTranslation('composition');
  return (
    <div data-testid="motif-empty" className="flex flex-col items-center gap-3 p-6 text-center">
      <div className="text-2xl" aria-hidden="true">📚</div>
      <h3 className="text-sm font-medium text-neutral-800 dark:text-neutral-100">
        {t('motif.empty.title', { defaultValue: 'Your motif library is ready' })}
      </h3>
      <p className="max-w-md text-xs text-neutral-500 dark:text-neutral-400">
        {t('motif.empty.body', {
          defaultValue: 'Motifs are reusable plot shapes. The planner picks one per chapter so even a small model writes a solid scene. 12 starter motifs are already here — tu-tiên and báo-thù.',
        })}
      </p>
      {/* T21 — say what this is NOT. A 2026-09-06 run opened this panel expecting a tracker for
          the story's own recurring imagery (its steering rules name two such motifs by name),
          found a picker of generic cross-genre plot templates, and recorded the feature as
          missing. The copy below was accurate and still misread, because the panel is called
          "Motif Library" and "motif" means something else to an author. Renaming is a product
          decision with an 18-language ripple; saying what it is not costs nothing and answers the
          question at the moment it is asked. */}
      <p data-testid="motif-empty-not-themes" className="max-w-sm text-[11px] text-muted-foreground/80">
        {t('motif.empty.notThemes', {
          defaultValue:
            'These are STRUCTURAL plot shapes for the planner, not a tracker of the recurring '
            + 'images or themes in your own story — nothing here follows a symbol across your chapters.',
        })}
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <button
          type="button"
          data-testid="motif-empty-new"
          className="rounded bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700"
          onClick={onNewMotif}
        >
          {t('motif.action.newMotif', { defaultValue: '+ New motif' })}
        </button>
        <button
          type="button"
          data-testid="motif-empty-browse"
          className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-200 dark:hover:bg-neutral-800"
          onClick={onBrowseSystem}
        >
          {t('motif.empty.browseSystem', { defaultValue: 'Browse the 12 starters' })}
        </button>
      </div>
      <p className="text-[11px] text-neutral-400">
        {t('motif.empty.hint', { defaultValue: 'No tokens needed — building a motif by hand is free.' })}
      </p>
    </div>
  );
}
