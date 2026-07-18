// #09 Lane B — motif authoring effects (spec 33 / S4 · completeness-audit fix for §2 bar #5).
//
// The X-4 coverage ledger maps every composition_motif_* WRITE (create/patch/archive/adopt/bind/
// unbind/link_create/link_delete/mine) — plus the suggest read — to `motifEffects`. Until now the
// file did not exist (PENDING 'wave-3'), so an AGENT that created/bound/mined a motif left the
// human's open motif-library / graph / binding / conformance panels STALE until a manual refresh
// (the X-4 bug class). This registers the handler so an agent write refreshes them.
//
// ⚠ INVALIDATE BY PREFIX — the effect result does NOT reliably carry project_id/motif_id (same rule
// as compositionEffects/authoringRunEffects). Each prefix below matches every project/scope/chapter
// variant of its query family, so one agent write refreshes all open motif surfaces. Over-invalidation
// is a cheap refetch; a scoped miss would leave a stale panel — which is the bug.
import { registerEffectHandler, type EffectContext } from '@/features/studio/agent/effectRegistry';

let registered = false;

// The motif query families (see useMotifLibrary / useMotifLinks / useMotifBindings /
// useMotifCandidates / useMotifSuggestions). Prefix keys — the trailing scope/id/params match too.
const MOTIF_KEYS = [
  ['composition', 'motifs'],            // library list (my/book/shared/system/catalog/drafts)
  ['composition', 'motif-links'],       // the graph section (BE-M3)
  ['composition', 'motif-bindings'],    // per-chapter scene bindings (scene-inspector Motifs section)
  ['composition', 'motif-candidates'],  // the swap/bind picker
  ['composition', 'motif-suggest'],     // ranked suggest (BE-M4)
] as const;

export function motifEffect(ctx: EffectContext): void {
  for (const queryKey of MOTIF_KEYS) ctx.queryClient.invalidateQueries({ queryKey: [...queryKey] });
}

// The WRITE (+ suggest) families that mutate/derive motif state — EXPLICIT, not `/^composition_motif_/`,
// because the reads (composition_motif_get / _search / _book_list / _link_list) must NOT invalidate
// (the X-4 read-thrash guard reds on an over-broad pattern). Mirrors WRITE_TOOLS in the coverage ledger.
const MOTIF_WRITE_PATTERN =
  /^composition_motif_(create|patch|archive|adopt|bind|unbind|link_create|link_delete|mine|suggest_for_chapter)/;

/** Idempotent — register the motif effect handler once (§8.0b one-file-per-family).
 *  Disjointness: the pattern matches only motif writes + suggest, and NO other family (canon_rule_/
 *  create_work/generate/arc_/authoring_run_/outline_node/scene_link/prose/draft lack the token). */
export function registerMotifEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(MOTIF_WRITE_PATTERN, motifEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetMotifEffectHandlers(): void {
  registered = false;
}
