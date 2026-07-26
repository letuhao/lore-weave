// #09 Lane B — the flywheel (S6/M5). An agent `composition_publish` triggers the extraction that
// grows canon; the flywheel panel renders that delta. So when the agent publishes, invalidate the
// flywheel query — the panel then refetches (and its own poll catches the delta when the async
// extraction lands, since the delta is NOT ready at publish-confirm time; E2). §8.0b: `flywheel` is its
// OWN tool-family here (the ledger re-partition split it out of the mis-lumped compositionEffects).
import { registerEffectHandler, type EffectContext } from '../effectRegistry';

let registered = false;

export function flywheelPublishEffect(ctx: EffectContext): void {
  // Prefix invalidate (the effect result doesn't reliably carry project_id; over-invalidation is a
  // cheap refetch, a project-scoped miss is the stale-panel bug — same rule as the other handlers).
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'flywheel'] });
}

/** Idempotent — register the flywheel publish effect once. Double-fire check (§8.0b):
 *  /^composition_publish$/ is exact and matches no other pattern (canon_rule_/authoring_run_/arc_/
 *  outline_node_/scene_link_/create_work), so it is DISJOINT. Safe. */
export function registerFlywheelEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(/^composition_publish$/, flywheelPublishEffect);
}

/** Test-only: undo the idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetFlywheelEffectHandlers(): void {
  registered = false;
}
