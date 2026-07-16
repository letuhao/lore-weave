// #09 Lane B — composition authoring effects (spec 31 / §8.0b: canon, corrections, style, voice).
//
// The domain is the TOOL FAMILY, not the panel. This file owns the composition WRITE tools whose
// results a Studio panel renders — starting with the canon-rule family (S6 quality-canon-rules +
// quality-canon). When an AGENT creates/updates/deletes/restores a canon rule, the human's open
// canon panels must refetch, not show stale state until a manual refresh (the X-4 bug class).
//
// SCOPE NOTE (why publish/conformance are NOT here): the X-4 coverage ledger originally lumped
// composition_publish + composition_conformance_run into this file. That conflated three cross-session
// tool families into one — against §8.0b's one-file-per-family rule. They are re-mapped to their own
// pending files (flywheelEffects = S6/M5; conformanceEffects = S4), which stay PENDING until those
// panels ship. This file clears ONLY the canon family it actually has a consumer for.
//
// ⚠ INVALIDATE BY PREFIX — the effect result does NOT reliably carry the project_id (same rule as
// authoringRunEffects). ['composition','canon'] prefix-matches every canon list query
// (['composition','canon',projectId,{includeArchived}], useCanonRules) AND the viewer's derived reads,
// so an agent write refreshes both the rules panel and the issues viewer. Over-invalidation is safe
// (a refetch); a project-scoped miss would leave a stale panel, which is the bug.
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

let registered = false;

const CANON_KEYS = [
  ['composition', 'canon'],   // useCanonRules list (all projects/variants) + quality-canon viewer
] as const;

export function compositionCanonEffect(ctx: EffectContext): void {
  for (const queryKey of CANON_KEYS) ctx.queryClient.invalidateQueries({ queryKey: [...queryKey] });
}

/** Idempotent — register the composition canon effect handler once.
 *  Double-fire check (§8.0b): /^composition_canon_rule_/ vs every existing pattern —
 *  /^composition_authoring_run_/ (no: `canon_rule` ≠ `authoring_run`), GLOSSARY/KNOWLEDGE/
 *  translation patterns (no: different prefixes). ⇒ DISJOINT. Safe. */
export function registerCompositionEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(/^composition_canon_rule_/, compositionCanonEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetCompositionEffectHandlers(): void {
  registered = false;
}
