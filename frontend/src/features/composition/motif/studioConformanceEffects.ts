// #09 Lane B — conformance effects (spec 33 / S4 · completeness-audit fix for §2 bar #5).
//
// The X-4 ledger maps composition_conformance_run → `conformanceEffects` (PENDING 's4' until the
// quality-conformance panel shipped — which it now has). When an AGENT re-runs conformance, the
// human's open quality-conformance trace (and the arc-conformance overlay) must refetch, not show
// the pre-run verdicts until a manual refresh (the X-4 bug class).
//
// ⚠ INVALIDATE BY PREFIX — the effect result does not reliably carry project_id/chapter_id. The two
// prefixes match every project/chapter/arc variant of the conformance queries (useConformanceTrace /
// useArcConformance), so one agent run refreshes both scopes.
import { registerEffectHandler, type EffectContext } from '@/features/studio/agent/effectRegistry';

let registered = false;

const CONFORMANCE_KEYS = [
  ['composition', 'conformance'],       // chapter-scope trace (useConformanceTrace → quality-conformance)
  ['composition', 'arc-conformance'],   // arc-scope overlay (useArcConformance)
] as const;

export function conformanceEffect(ctx: EffectContext): void {
  for (const queryKey of CONFORMANCE_KEYS) ctx.queryClient.invalidateQueries({ queryKey: [...queryKey] });
}

/** Idempotent — register the conformance effect handler once (§8.0b one-file-per-family).
 *  Disjointness: `/^composition_conformance_run/` matches ONLY the conformance-run tool; no other
 *  family carries that token (motif_ handler is `/^composition_motif_/`, canon is `canon_rule_`, …). */
export function registerConformanceEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(/^composition_conformance_run/, conformanceEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetConformanceEffectHandlers(): void {
  registered = false;
}
