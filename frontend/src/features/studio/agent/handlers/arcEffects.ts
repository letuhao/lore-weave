// 32 §6 step-8 (X-4) — Lane B for the arc spec tree. After ANY `composition_arc_*` agent write
// (create/update/delete/restore/move/assign_chapters, and Wave-4's apply/extract_template), refresh
// the plan-hub canvas + the arc shell + any open arc-inspector detail — via CODE (invalidate), never
// by pasting the tool result into state (G5). Without this, the agent edits an arc and the open
// inspector shows the STALE row, so the user's next save 412s against a version they never saw.
//
// 🔴 ONE HOME for `composition_arc_*` (32 §6 / 34 §6): a SINGLE broad `/^composition_arc_/`
// registration. matchEffectHandlers returns EVERY match and runEffectHandlers awaits ALL of them, so
// a second overlapping registration would double-fire and give one concept two homes. Wave 4 EXTENDS
// this handler's body (adds the arc-templates query key), it does NOT register a second pattern.
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

let registered = false;

export function arcEffect(ctx: EffectContext): void {
  // The shell + canvas (plan-hub) and the arc-inspector detail cache both derive from the arc rows.
  ctx.queryClient.invalidateQueries({ queryKey: ['plan-hub'] });
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'arcs', ctx.bookId] });
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'arc'] });
}

/** Idempotent — register the arc Lane-B handler once. */
export function registerArcEffectHandlers(): void {
  if (registered) return;
  registered = true;
  // Negative-lookahead excludes the READS (composition_arc_get/_list) — an effect on a chatty read
  // loop would thrash the query cache (the coverage ledger's READ_TOOLS guard reds on that).
  registerEffectHandler(/^composition_arc_(?!get|list)/, arcEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetArcEffectHandlers(): void {
  registered = false;
}
