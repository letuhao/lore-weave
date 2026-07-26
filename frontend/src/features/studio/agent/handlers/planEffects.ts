// Wave 5 (S3) — Lane B for PlanForge. After ANY `plan_*` agent WRITE (compile, run_pass,
// review_checkpoint, apply_revision, propose_spec, self_check, validate, link, handoff_autofix,
// interpret_feedback) the derived pass ledger changes, so the open Pass Rail must refresh — via
// CODE (invalidate), never by pasting the tool result into state (G5). Without this, the agent
// runs a pass or approves the cast and the rail keeps showing the STALE row: the user cannot tell
// the compiler moved. (This is exactly why usePassRail is a react-query query, not useState — a
// hand-rolled ledger would be unreachable from this invalidate, making the handler a silent no-op.)
//
// ONE HOME for `plan_*`: a SINGLE broad `/^plan_(?!pass_status)/` registration. The negative
// lookahead excludes the READ (`plan_pass_status`) — an effect on a chatty read loop would thrash
// the cache (the coverage ledger's READ_TOOLS guard reds on that).
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

let registered = false;

export function planEffect(ctx: EffectContext): void {
  // The ledger (all runs of this book) + the "latest run" resolver both derive from plan-run state;
  // a compile mints a new run, a pass/checkpoint changes the derived view of the current one.
  ctx.queryClient.invalidateQueries({ queryKey: ['plan-passes'] });
  ctx.queryClient.invalidateQueries({ queryKey: ['plan-runs-latest', ctx.bookId] });
}

/** Idempotent — register the plan Lane-B handler once. */
export function registerPlanEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(/^plan_(?!pass_status)/, planEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetPlanEffectHandlers(): void {
  registered = false;
}
