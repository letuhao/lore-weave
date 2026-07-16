// The coverage ledger proves the plan_* WRITES match this handler and plan_pass_status (READ) does
// not; this proves the handler invalidates the RIGHT keys so an agent's plan_run_pass /
// plan_review_checkpoint actually refreshes the human's open Pass Rail (bar §2 #5 — agent parity).
import { describe, it, expect, vi } from 'vitest';
import { planEffect, registerPlanEffectHandlers, _resetPlanEffectHandlers } from '../planEffects';
import { clearEffectHandlers, matchEffectHandlers } from '../../effectRegistry';
import type { EffectContext } from '../../effectRegistry';

describe('planEffect', () => {
  it('invalidates the pass-rail ledger + latest-run resolver', () => {
    const invalidateQueries = vi.fn();
    planEffect({ bookId: 'b1', queryClient: { invalidateQueries } } as unknown as EffectContext);
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['plan-passes'] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['plan-runs-latest', 'b1'] });
  });

  it('registers a pattern that matches plan_* writes but NOT the plan_pass_status read', () => {
    clearEffectHandlers();
    _resetPlanEffectHandlers();
    registerPlanEffectHandlers();
    expect(matchEffectHandlers('plan_run_pass').length).toBeGreaterThanOrEqual(1);
    expect(matchEffectHandlers('plan_review_checkpoint').length).toBeGreaterThanOrEqual(1);
    expect(matchEffectHandlers('plan_compile').length).toBeGreaterThanOrEqual(1);
    // the READ must NOT fire an effect (a chatty status poll would thrash the cache)
    expect(matchEffectHandlers('plan_pass_status').length).toBe(0);
    clearEffectHandlers();
    _resetPlanEffectHandlers();
  });
});
