// C8 / SD-C8 (SD-7) — the trend-exclusion rule for coaching scorecards.
//
// A coaching score is QUARANTINE-tier: shown to the user, but NEVER plotted on a trend line, until a
// human-rating milestone certifies the scorer (SD-7). Every score a self-run produces is quarantine=true
// (fail-closed). So a trend line must be built ONLY from non-quarantine scorecards — and today that set
// is empty, which is correct: no trend is drawn from an uncertified score. This is the single home for
// that rule so the FE can never accidentally trend a quarantine score.
import type { Scorecard } from './types';

/** The scorecards eligible for a TREND line — quarantine scores are excluded (SD-7). */
export function scorecardsForTrend(cards: Scorecard[]): Scorecard[] {
  return cards.filter((c) => !c.quarantine);
}

/** Whether a trend line may be drawn at all (at least 2 non-quarantine points). Quarantine-only ⇒ false. */
export function canShowTrend(cards: Scorecard[]): boolean {
  return scorecardsForTrend(cards).length >= 2;
}
