import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const deriveWorkMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: { deriveWork: (...a: unknown[]) => deriveWorkMock(...a) },
}));

import { useDivergenceWizard } from '../useDivergenceWizard';
import { derivativeContextKey } from '../useDerivativeContext';
import type { Work } from '../../types';

const sourceWork: Work = {
  project_id: 'src-proj', user_id: 'u1', book_id: 'book-1',
  active_template_id: null, status: 'active', settings: {}, version: 1,
};

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, qc };
}

beforeEach(() => deriveWorkMock.mockReset());

describe('useDivergenceWizard (C24 — 4-step → POST /works/{id}/derive)', () => {
  it('starts at step 1 and advances via EXPLICIT goNext callbacks (no useEffect)', () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useDivergenceWizard({ sourceWork, token: 'tok' }), { wrapper: Wrapper });
    expect(result.current.step).toBe(1);
    act(() => result.current.goNext());
    expect(result.current.step).toBe(2);
    act(() => result.current.goNext());
    act(() => result.current.goNext());
    expect(result.current.step).toBe(4);
    // clamps at 4
    act(() => result.current.goNext());
    expect(result.current.step).toBe(4);
    act(() => result.current.goBack());
    expect(result.current.step).toBe(3);
  });

  it('buildBody maps a genderbend (character_transform) + branch + override + canon rule to the derive body', () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useDivergenceWizard({ sourceWork, token: 'tok' }), { wrapper: Wrapper });
    act(() => {
      result.current.setName('  Genderbend AU  '); // BE-13a: must be sent (trimmed), not dropped
      result.current.setBranchPoint(3);
      result.current.setTaxonomy('character_transform');
      result.current.setOverride('ent-zrc', { description: 'now a woman' });
      result.current.setCanonRules(['张若尘 is female', '  ']); // blank trimmed out
    });
    const body = result.current.buildBody();
    expect(body.name).toBe('Genderbend AU'); // BE-13a — the name reaches the derive body, trimmed
    expect(body.branch_point).toBe(3);
    expect(body.divergence.taxonomy).toBe('character_transform');
    expect(body.divergence.canon_rule).toEqual(['张若尘 is female']);
    expect(body.entity_overrides).toEqual([
      { target_entity_id: 'ent-zrc', overridden_fields: { description: 'now a woman' } },
    ]);
  });

  it('clearing an override drops it from the OVERRIDDEN set', () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useDivergenceWizard({ sourceWork, token: 'tok' }), { wrapper: Wrapper });
    act(() => result.current.setOverride('e1', { description: 'x' }));
    expect(Object.keys(result.current.overrides)).toEqual(['e1']);
    act(() => result.current.setOverride('e1', null));
    expect(result.current.overrides).toEqual({});
  });

  it('step 4 cannot advance/submit without a name; submit posts deriveWork with the source project_id', async () => {
    deriveWorkMock.mockResolvedValue({ project_id: 'deriv-proj', source_work_id: 'srcwork', branch_point: 3 });
    const onDerived = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useDivergenceWizard({ sourceWork, token: 'tok', onDerived }), { wrapper: Wrapper });
    act(() => result.current.goTo(4));
    expect(result.current.canAdvance).toBe(false);
    act(() => result.current.submit()); // no-op without a name
    expect(deriveWorkMock).not.toHaveBeenCalled();
    act(() => { result.current.setName('Genderbend AU'); result.current.setTaxonomy('character_transform'); });
    expect(result.current.canAdvance).toBe(true);
    act(() => result.current.submit());
    await waitFor(() => expect(onDerived).toHaveBeenCalled());
    expect(deriveWorkMock).toHaveBeenCalledWith('src-proj', expect.objectContaining({
      divergence: expect.objectContaining({ taxonomy: 'character_transform' }),
    }), 'tok');
    expect(onDerived).toHaveBeenCalledWith(expect.objectContaining({ project_id: 'deriv-proj' }));
  });

  it('on success invalidates the DURABLE derivative-context key (WS-B2 — no ephemeral stash)', async () => {
    deriveWorkMock.mockResolvedValue({ project_id: 'deriv-proj', source_work_id: 'srcwork' });
    const { Wrapper, qc } = makeWrapper();
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    const { result } = renderHook(() => useDivergenceWizard({ sourceWork, token: 'tok' }), { wrapper: Wrapper });
    act(() => { result.current.setName('AU'); result.current.setOverride('e1', { description: 'x' }); });
    act(() => result.current.submit());
    await waitFor(() => expect(deriveWorkMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: derivativeContextKey('deriv-proj') }),
    );
  });
});
