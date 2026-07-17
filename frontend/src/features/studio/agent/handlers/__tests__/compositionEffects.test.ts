// The ledger (effectCoverage.contract.test.ts) proves the canon tools MATCH this handler; this proves
// the handler invalidates the RIGHT key, so an agent canon-rule write actually refreshes the human's
// open quality-canon-rules / quality-canon panels (bar §2 #5 — agent parity).
import { describe, it, expect, vi } from 'vitest';
import { compositionCanonEffect, compositionDivergenceEditEffect } from '../compositionEffects';
import type { EffectContext } from '../../effectRegistry';

describe('compositionCanonEffect', () => {
  it('invalidates the composition canon query family', () => {
    const invalidateQueries = vi.fn();
    compositionCanonEffect({ queryClient: { invalidateQueries } } as unknown as EffectContext);
    // Prefix key — matches useCanonRules(['composition','canon',pid,{includeArchived}]) AND the viewer.
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['composition', 'canon'] });
  });
});

describe('compositionDivergenceEditEffect (S-04)', () => {
  it('invalidates the derivative-context + entity-overrides families so an agent edit refreshes the panel', () => {
    const invalidateQueries = vi.fn();
    compositionDivergenceEditEffect({ queryClient: { invalidateQueries } } as unknown as EffectContext);
    // Prefix keys — match useDivergenceManager.spec (['composition','derivative-context',pid]) AND
    // useDivergenceSpecEditor.overrides (['composition','entity-overrides',pid]) for every open branch.
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['composition', 'derivative-context'] });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['composition', 'entity-overrides'] });
  });
});
