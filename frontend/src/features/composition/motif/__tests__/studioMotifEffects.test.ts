// S4 completeness-audit fix (§2 bar #5, agent parity): an agent motif/conformance write must
// refresh the human's open panels via the Lane-B effect handler — proven by EFFECT (the right
// query prefixes are invalidated), not just by registration.
import { describe, it, expect, vi } from 'vitest';
import { motifEffect } from '../studioMotifEffects';
import { conformanceEffect } from '../studioConformanceEffects';
import type { EffectContext } from '@/features/studio/agent/effectRegistry';

function fakeCtx() {
  const invalidateQueries = vi.fn();
  const ctx = { queryClient: { invalidateQueries } } as unknown as EffectContext;
  return { ctx, invalidateQueries };
}

describe('motifEffect (agent parity)', () => {
  it('invalidates every motif query family (library/graph/bindings/candidates/suggest)', () => {
    const { ctx, invalidateQueries } = fakeCtx();
    motifEffect(ctx);
    const keys = invalidateQueries.mock.calls.map((c) => (c[0] as { queryKey: string[] }).queryKey);
    expect(keys).toContainEqual(['composition', 'motifs']);
    expect(keys).toContainEqual(['composition', 'motif-links']);
    expect(keys).toContainEqual(['composition', 'motif-bindings']);
    expect(keys).toContainEqual(['composition', 'motif-candidates']);
    expect(keys).toContainEqual(['composition', 'motif-suggest']);
  });
});

describe('conformanceEffect (agent parity)', () => {
  it('invalidates the chapter + arc conformance query families', () => {
    const { ctx, invalidateQueries } = fakeCtx();
    conformanceEffect(ctx);
    const keys = invalidateQueries.mock.calls.map((c) => (c[0] as { queryKey: string[] }).queryKey);
    expect(keys).toContainEqual(['composition', 'conformance']);
    expect(keys).toContainEqual(['composition', 'arc-conformance']);
  });
});
