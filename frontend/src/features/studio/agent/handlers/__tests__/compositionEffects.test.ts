// The ledger (effectCoverage.contract.test.ts) proves the canon tools MATCH this handler; this proves
// the handler invalidates the RIGHT key, so an agent canon-rule write actually refreshes the human's
// open quality-canon-rules / quality-canon panels (bar §2 #5 — agent parity).
import { describe, it, expect, vi } from 'vitest';
import { compositionCanonEffect } from '../compositionEffects';
import type { EffectContext } from '../../effectRegistry';

describe('compositionCanonEffect', () => {
  it('invalidates the composition canon query family', () => {
    const invalidateQueries = vi.fn();
    compositionCanonEffect({ queryClient: { invalidateQueries } } as unknown as EffectContext);
    // Prefix key — matches useCanonRules(['composition','canon',pid,{includeArchived}]) AND the viewer.
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['composition', 'canon'] });
  });
});
