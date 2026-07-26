// W6 §3.4 — the co-write top-N swap picker. Focus-trapped popover (Esc closes,
// focus returns); becomes a bottom-sheet on mobile (§5.5 — handled by the parent's
// responsive container). Each candidate shows its name + match summary. Render-only.
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { MotifCandidateOption } from './MotifBindingCard';

type Props = {
  open: boolean;
  candidates: MotifCandidateOption[];
  swapping: boolean;
  onSwap: (motifId: string) => void;
  onClose: () => void;
};

export function SwapMotifPopover({ open, candidates, swapping, onSwap, onClose }: Props) {
  const { t } = useTranslation('composition');
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (open) ref.current?.focus(); }, [open]);
  if (!open) return null;

  return (
    <div
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-label={t('motif.swap.title', { defaultValue: 'Swap motif' })}
      tabIndex={-1}
      data-testid="motif-swap-popover"
      className="z-40 mt-1 max-h-64 w-full overflow-auto rounded border border-neutral-300 bg-white p-1 shadow-lg outline-none dark:border-neutral-600 dark:bg-neutral-900"
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
    >
      {candidates.length === 0 ? (
        <p className="p-2 text-xs text-neutral-500">{t('motif.swap.none', { defaultValue: 'No other matches.' })}</p>
      ) : (
        candidates.map((c) => (
          <button
            key={c.motif_id}
            type="button"
            data-testid={`motif-swap-option-${c.motif_id}`}
            className="flex w-full flex-col items-start gap-0.5 rounded px-2 py-1.5 text-left text-xs hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
            disabled={swapping}
            onClick={() => onSwap(c.motif_id)}
          >
            <span className="font-medium text-neutral-800 dark:text-neutral-100">{c.motif_name}</span>
            {c.summary && <span className="text-neutral-500">{c.summary}</span>}
          </button>
        ))
      )}
    </div>
  );
}
