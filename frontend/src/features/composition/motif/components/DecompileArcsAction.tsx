// S-10 O6c — "Group my chapters into arcs". composition_decompile_arcs was confirm-gated to the
// agent with no FE. This is the human button: it runs the deterministic decompiler (a REST twin of
// the agent tool — a human click is the approval, so no confirm-token dance) after an inline
// "are you sure" step, since it writes an arc layer over the book's chapters. Idempotent (re-running
// reuses arcs by position), so a re-click is safe. Self-contained action widget (house pattern).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useDecompileArcs } from '../hooks/useDecompileArcs';

type Props = {
  bookId: string | null;
  token: string | null;
};

const CHAPTERS_PER_ARC = 10;

export function DecompileArcsAction({ bookId, token }: Props) {
  const { t } = useTranslation('composition');
  const dec = useDecompileArcs(bookId, token);
  const [confirming, setConfirming] = useState(false);

  if (!bookId) return null;

  return (
    <div data-testid="decompile-arcs-action" className="flex flex-col gap-1.5">
      {!confirming && !dec.result && (
        <button
          type="button"
          data-testid="decompile-open"
          disabled={dec.isPending}
          className="self-start rounded border px-2 py-0.5 text-[11px] hover:bg-secondary disabled:opacity-50"
          onClick={() => setConfirming(true)}
        >
          {t('motif.arc.decompile.open', { defaultValue: 'Group chapters into arcs' })}
        </button>
      )}

      {confirming && !dec.result && (
        <div data-testid="decompile-confirm" className="flex flex-col gap-1.5 rounded border border-amber-400 bg-amber-50 p-2 dark:border-amber-700 dark:bg-amber-900/20">
          <p className="text-[11px] text-amber-700 dark:text-amber-300">
            {t('motif.arc.decompile.confirm', {
              n: CHAPTERS_PER_ARC,
              defaultValue: 'Automatically group this book’s chapters into arcs (~{{n}} chapters each). Safe to re-run — existing arcs are reused.',
            })}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="decompile-run"
              disabled={dec.isPending}
              className="rounded bg-amber-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              onClick={() => dec.run(CHAPTERS_PER_ARC)}
            >
              {dec.isPending
                ? t('motif.arc.decompile.running', { defaultValue: 'Grouping…' })
                : t('motif.arc.decompile.run', { defaultValue: 'Group into arcs' })}
            </button>
            <button
              type="button"
              data-testid="decompile-cancel"
              className="text-[11px] text-muted-foreground hover:underline"
              onClick={() => { setConfirming(false); dec.reset(); }}
            >
              {t('motif.arc.decompile.cancel', { defaultValue: 'Cancel' })}
            </button>
          </div>
          {dec.isError && (
            <p role="alert" data-testid="decompile-error" className="text-[10px] text-destructive">
              {t('motif.arc.decompile.error', { defaultValue: 'Could not group the chapters into arcs.' })}
            </p>
          )}
        </div>
      )}

      {dec.result && (
        <p data-testid="decompile-done" className="text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
          {dec.result.arcs > 0
            ? t('motif.arc.decompile.done', {
                arcs: dec.result.arcs, chapters: dec.result.chapters_assigned,
                defaultValue: 'Grouped {{chapters}} chapters into {{arcs}} arcs.',
              })
            : t('motif.arc.decompile.none', { defaultValue: 'No chapters to group into arcs yet.' })}
        </p>
      )}
    </div>
  );
}
