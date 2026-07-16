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

// S1-A3 (completeness audit) — the WORK-RESOLUTION family the scene-compose / chapter-assemble panels
// render from. The outline/scene writes are already covered by bookEffects (/^composition_(outline_node|
// scene_link)_/); the remaining hole was `create_work` (an agent setting up the co-writer Work while
// the human stares at "No co-writer Work yet") and `generate` (an agent drafting a scene → the scene's
// status/content shifts). Both were UNMATCHED by every pattern (verified), so an agent write left the
// human's Work-setup CTA + scene selector stale. Prefix-invalidate work + outline (over-invalidation is
// a cheap refetch; the effect result doesn't reliably carry project_id). The human's OWN generate goes
// through the panel stream, not a Lane-B agent tool-call, so this never thrashes the human's typing.
const WORK_KEYS = [
  ['composition', 'work'],     // useWorkResolution — the resolved Work (composition_create_work)
  ['composition', 'outline'],  // useChapterScenes / outline children — the scene selector + stitch gate
] as const;

export function compositionWorkEffect(ctx: EffectContext): void {
  for (const queryKey of WORK_KEYS) ctx.queryClient.invalidateQueries({ queryKey: [...queryKey] });
}

/** Idempotent — register the composition effect handlers once.
 *  Double-fire check (§8.0b): `canon_rule_` vs `(create_work|generate)` — DISJOINT; and neither
 *  overlaps any existing pattern — bookEffects `/^composition_.*(prose|draft)/` (no: create_work/
 *  generate carry neither token) or `/^composition_(outline_node|scene_link)_/` (no), arcEffects
 *  `/^composition_arc_/` (no), authoringRunEffects `/^composition_authoring_run_/` (no). ⇒ each tool
 *  matches AT MOST one handler. READS (`composition_get_*`, `composition_list_outline`) match neither. */
export function registerCompositionEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(/^composition_canon_rule_/, compositionCanonEffect);
  // S5 (D-DIVERGENCE-MCP-TOOLS) — `archive_derivative` removes a dị bản from the book's Work set;
  // the divergence manage panel + every active-work resolver read ['composition','work'], so an
  // agent archive must refresh them (same WORK_KEYS as create_work). Pattern is `archive_derivative`
  // (NOT `_derivative` broad) so the READ `composition_list_derivatives` matches NO handler.
  registerEffectHandler(/^composition_(create_work|generate|archive_derivative)/, compositionWorkEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetCompositionEffectHandlers(): void {
  registered = false;
}
