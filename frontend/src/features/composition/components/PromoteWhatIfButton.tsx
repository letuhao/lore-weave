// C27 (dị bản M4) — "Promote this what-if to a saved dị bản" affordance (view only).
// Surfaces when the writer is exploring an EPHEMERAL what-if and wants to MATERIALIZE
// it into a PERSISTENT derivative Work. The promotion routes through the C23 derive
// path (fresh project_id + spec + overrides carried over) via useWhatIfPromotion.
//
// View-only (React-MVC): all logic lives in useWhatIfPromotion. The promote button is
// an explicit onClick → controller callback (no useEffect-for-events).
import { useTranslation } from 'react-i18next';
import { useWhatIfPromotion, type WhatIfDraft } from '../hooks/useWhatIfPromotion';
import type { Work } from '../types';

type Props = {
  /** The SOURCE (canon) Work the what-if branches from. */
  sourceWork: Work;
  /** The ephemeral what-if exploration to promote. */
  draft: WhatIfDraft;
  token: string | null;
  /** Routed the materialized persistent derivative. */
  onPromoted?: (derivative: Work) => void;
};

export function PromoteWhatIfButton({ sourceWork, draft, token, onPromoted }: Props) {
  const { t } = useTranslation('composition');
  const p = useWhatIfPromotion({ sourceWork, draft, token, onPromoted });

  return (
    <div className="flex flex-col gap-1" data-testid="promote-whatif">
      <div className="flex items-center gap-2">
        <span
          data-testid="promote-whatif-ephemeral-badge"
          className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
        >
          {t('promote.ephemeral', { defaultValue: 'What-if (exploring)' })}
        </span>
        <button
          type="button"
          data-testid="promote-whatif-action"
          className="rounded bg-purple-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
          onClick={p.promote}
          disabled={!p.canPromote || p.isPromoting || !token}
          title={t('promote.actionHint', {
            defaultValue: 'Save this what-if as a persistent dị bản with its own knowledge graph',
          })}
        >
          {p.isPromoting
            ? t('promote.promoting', { defaultValue: 'Promoting…' })
            : t('promote.action', { defaultValue: 'Promote to dị bản' })}
        </button>
      </div>
      {!p.canPromote && (
        <span className="text-[11px] text-neutral-500 dark:text-neutral-400">
          {t('promote.needsName', { defaultValue: 'Name the what-if to promote it.' })}
        </span>
      )}
      {p.error && (
        <span data-testid="promote-whatif-error" className="text-[11px] text-red-600 dark:text-red-400">
          {p.error}
        </span>
      )}
    </div>
  );
}
