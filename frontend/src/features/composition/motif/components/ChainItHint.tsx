// W6 §3.4 — the legal-succession "chain it" affordance (pre-seed the next chapter
// with a motif that legally follows this one). Render-only.
import { useTranslation } from 'react-i18next';
import type { SuccessionHint } from '../types';

export function ChainItHint({ hint, onChain }: { hint: SuccessionHint; onChain: (h: SuccessionHint) => void }) {
  const { t } = useTranslation('composition');
  return (
    <div data-testid="motif-chain-it" className="flex items-center justify-between gap-2 rounded border border-indigo-200 bg-indigo-50 px-2 py-1 text-[11px] dark:border-indigo-900 dark:bg-indigo-950/30">
      <span className="text-indigo-700 dark:text-indigo-300">
        {t('motif.chain.hint', { name: hint.to_motif_name, defaultValue: 'Next: "{{name}}" follows naturally.' })}
      </span>
      <button
        type="button"
        data-testid="motif-chain-it-btn"
        className="shrink-0 rounded bg-indigo-600 px-2 py-0.5 font-medium text-white hover:bg-indigo-700"
        onClick={() => onChain(hint)}
      >
        {t('motif.chain.action', { defaultValue: 'Chain it' })}
      </button>
    </div>
  );
}
