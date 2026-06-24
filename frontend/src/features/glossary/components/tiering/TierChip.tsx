// G6 — tier provenance chip (System slate / User indigo / Book sky).
import type { Tier } from '../../tieringTypes';
import { TIER_CHIP_CLASS, TIER_LABEL } from '../../lib/tiering';

export function TierChip({ tier, className = '' }: { tier: Tier; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1 py-0.5 text-[10px] font-semibold ${TIER_CHIP_CLASS[tier]} ${className}`}
      data-testid={`tier-chip-${tier}`}
    >
      {TIER_LABEL[tier]}
    </span>
  );
}
