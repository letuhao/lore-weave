// W6 §3.4 (mockup 03 — the ★ core value) — the per-scene bound-motif card rendered
// inside W2's PlannerView (the seam, MD-1: W6 ships it, W2 renders it). Shows the
// bound motif, its match_reason, the role bindings, swap/clear/chain affordances,
// the overuse warning, and the bind→COMMIT→GENERATE link. A null motif renders the
// free-form fallback (the A3 invent path — NOT an error). Render-only; the parent
// (W2) supplies the data + the useMotifBinding callbacks.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { BoundMotif, OveruseWarning, SuccessionHint } from '../types';
import type { RosterOption } from '../../hooks/useGlossaryRoster';
import { MatchReasonChip } from './MatchReasonChip';
import { RoleBindingRow } from './RoleBindingRow';
import { SwapMotifPopover } from './SwapMotifPopover';
import { OveruseBanner } from './OveruseBanner';
import { ChainItHint } from './ChainItHint';
import { InfoAsymmetryCard } from './InfoAsymmetryCard';
import type { InfoAsymmetry } from '../types';

export type MotifCandidateOption = { motif_id: string; motif_name: string; summary?: string };

type Props = {
  sceneId: string;
  bound: BoundMotif | null;
  infoAsymmetry?: InfoAsymmetry | null;
  candidates?: MotifCandidateOption[];
  overuse?: OveruseWarning | null;
  succession?: SuccessionHint | null;
  roster?: RosterOption[];
  swapping?: boolean;
  onSwap: (motifId: string) => void;
  onClear: () => void;
  onRebindRole: (roleKey: string, entityId: string) => void;
  onChain: (hint: SuccessionHint) => void;
  /** §4.6 — commit the binding + route to generate (W2 wires the route). */
  onCommitAndGenerate: (sceneId: string) => void;
};

export function MotifBindingCard({
  sceneId, bound, infoAsymmetry, candidates = [], overuse, succession, roster = [],
  swapping, onSwap, onClear, onRebindRole, onChain, onCommitAndGenerate,
}: Props) {
  const { t } = useTranslation('composition');
  const [swapOpen, setSwapOpen] = useState(false);

  // free-form fallback — NOT an error (the A3 invent path, §4.1). A scene CAN still
  // be bound from here (D-MOTIF-FE-SWAP-NODE-GRANULARITY — the per-scene bind BE):
  // "Bind motif" opens the same picker as swap and PATCHes a per-scene application.
  if (!bound || bound.motif_id == null) {
    return (
      <div data-testid={`motif-binding-${sceneId}`} data-state="free-form" className="rounded border border-dashed border-neutral-300 p-2 text-xs text-neutral-500 dark:border-neutral-600">
        <div className="flex items-center justify-between gap-2">
          <span>{t('motif.binding.freeForm', { defaultValue: 'No motif matched — this scene is free-form.' })}</span>
          {candidates.length > 0 && (
            <button
              type="button"
              data-testid={`motif-binding-bind-${sceneId}`}
              aria-haspopup="dialog"
              className="shrink-0 rounded border border-amber-400 px-1.5 py-0.5 text-[11px] text-amber-700 disabled:opacity-50 dark:text-amber-300"
              disabled={swapping}
              onClick={() => setSwapOpen((v) => !v)}
            >
              {t('motif.action.bind', { defaultValue: 'Bind motif' })}
            </button>
          )}
        </div>
        <SwapMotifPopover
          open={swapOpen}
          candidates={candidates}
          swapping={!!swapping}
          onSwap={(id) => { onSwap(id); setSwapOpen(false); }}
          onClose={() => setSwapOpen(false)}
        />
      </div>
    );
  }

  return (
    <div data-testid={`motif-binding-${sceneId}`} data-state="bound" className="flex flex-col gap-1.5 rounded border border-amber-200 bg-amber-50/40 p-2 dark:border-amber-800 dark:bg-amber-950/20">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-amber-800 dark:text-amber-200">{bound.motif_name}</span>
        <div className="flex items-center gap-1">
          <button type="button" data-testid={`motif-binding-swap-${sceneId}`} aria-haspopup="dialog" className="rounded border border-amber-400 px-1.5 py-0.5 text-[11px] text-amber-700 dark:text-amber-300" onClick={() => setSwapOpen((v) => !v)}>
            {t('motif.action.swap', { defaultValue: 'Swap' })}
          </button>
          <button type="button" data-testid={`motif-binding-clear-${sceneId}`} className="rounded border border-neutral-300 px-1.5 py-0.5 text-[11px] text-neutral-500 dark:border-neutral-600" onClick={onClear}>
            {t('motif.action.clear', { defaultValue: 'Free-form' })}
          </button>
        </div>
      </div>

      <MatchReasonChip reason={bound.match_reason} />

      <SwapMotifPopover
        open={swapOpen}
        candidates={candidates}
        swapping={!!swapping}
        onSwap={(id) => { onSwap(id); setSwapOpen(false); }}
        onClose={() => setSwapOpen(false)}
      />

      {/* role bindings */}
      {Object.entries(bound.role_bindings).length > 0 && (
        <div className="flex flex-col gap-0.5">
          {Object.entries(bound.role_bindings).map(([roleKey, b]) => (
            <RoleBindingRow
              key={roleKey}
              roleKey={roleKey}
              roleLabel={roleKey}
              binding={b}
              options={roster}
              onPick={(entityId) => onRebindRole(roleKey, entityId)}
            />
          ))}
        </div>
      )}

      {infoAsymmetry && <InfoAsymmetryCard info={infoAsymmetry} />}
      {overuse && <OveruseBanner warning={overuse} />}
      {succession && <ChainItHint hint={succession} onChain={onChain} />}

      {/* §4.6 — the bind→COMMIT→GENERATE link (closes the H-8 dead-end) */}
      <button
        type="button"
        data-testid={`motif-binding-generate-${sceneId}`}
        className="mt-0.5 rounded bg-amber-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-amber-700"
        onClick={() => onCommitAndGenerate(sceneId)}
      >
        {t('motif.binding.commitGenerate', { defaultValue: 'Commit + write this scene →' })}
      </button>
    </div>
  );
}
