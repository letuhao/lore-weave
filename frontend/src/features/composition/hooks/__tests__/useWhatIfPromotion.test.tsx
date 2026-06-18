// C27 (dị bản M4) — what-if → derivative promotion tests. Proves: the ephemeral
// what-if's spec + overrides carry over to the C23 derive body with NONE dropped;
// promotion routes through compositionApi.deriveWork (the one C23 path); a reused
// (source) project_id from the BE is surfaced as an error (G2 fresh-project guard).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const deriveWorkMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: { deriveWork: (...a: unknown[]) => deriveWorkMock(...a) },
}));

import {
  useWhatIfPromotion,
  whatIfToDeriveBody,
  type WhatIfDraft,
} from '../useWhatIfPromotion';
import { derivativeOverridesKey } from '../useDerivativeContext';
import type { Work } from '../../types';

const sourceWork: Work = {
  project_id: 'src-proj', user_id: 'u1', book_id: 'book-1',
  active_template_id: null, status: 'active', settings: {}, version: 1,
};

const fullDraft: WhatIfDraft = {
  branchPoint: 3,
  taxonomy: 'character_transform',
  povAnchor: 'pov-ent',
  canonRules: ['张若尘 is female', '   '], // blank trimmed
  overrides: { 'ent-zrc': { description: 'now a woman' } },
  name: 'Genderbend AU',
};

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, qc };
}

beforeEach(() => deriveWorkMock.mockReset());

describe('whatIfToDeriveBody (pure mapping — nothing dropped)', () => {
  it('carries branch + taxonomy + pov_anchor + canon rules + overrides through', () => {
    const body = whatIfToDeriveBody(fullDraft);
    expect(body.branch_point).toBe(3);
    expect(body.divergence.taxonomy).toBe('character_transform');
    expect(body.divergence.pov_anchor).toBe('pov-ent');
    expect(body.divergence.canon_rule).toEqual(['张若尘 is female']); // blank dropped
    expect(body.entity_overrides).toEqual([
      { target_entity_id: 'ent-zrc', overridden_fields: { description: 'now a woman' } },
    ]);
  });
});

describe('useWhatIfPromotion (C27 — ephemeral → C23 derive)', () => {
  it('promote() materializes via deriveWork with the full carried-over body', async () => {
    deriveWorkMock.mockResolvedValue({ ...sourceWork, project_id: 'fresh-deriv-proj', source_work_id: 'src-id' });
    const onPromoted = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useWhatIfPromotion({ sourceWork, draft: fullDraft, token: 'tok', onPromoted }),
      { wrapper: Wrapper },
    );
    expect(result.current.canPromote).toBe(true);
    act(() => result.current.promote());
    await waitFor(() => expect(onPromoted).toHaveBeenCalled());
    // routed through the C23 derive path keyed on the SOURCE project.
    expect(deriveWorkMock).toHaveBeenCalledTimes(1);
    const [srcProj, body, tok] = deriveWorkMock.mock.calls[0];
    expect(srcProj).toBe('src-proj');
    expect(tok).toBe('tok');
    // spec + overrides carried over, none dropped.
    expect(body.branch_point).toBe(3);
    expect(body.entity_overrides).toHaveLength(1);
    expect(body.divergence.canon_rule).toEqual(['张若尘 is female']);
    // the materialized derivative has a FRESH project_id, distinct from the source.
    expect(onPromoted.mock.calls[0][0].project_id).toBe('fresh-deriv-proj');
  });

  it('stashes the submitted override set keyed by the FRESH derivative project (G2)', async () => {
    deriveWorkMock.mockResolvedValue({ ...sourceWork, project_id: 'fresh-deriv-proj', source_work_id: 'src-id' });
    const { Wrapper, qc } = makeWrapper();
    const { result } = renderHook(
      () => useWhatIfPromotion({ sourceWork, draft: fullDraft, token: 'tok' }),
      { wrapper: Wrapper },
    );
    act(() => result.current.promote());
    await waitFor(() => expect(deriveWorkMock).toHaveBeenCalled());
    await waitFor(() => {
      const meta = qc.getQueryData(derivativeOverridesKey('fresh-deriv-proj'));
      expect(meta).toEqual({ sourceProjectId: 'src-proj', overrideIds: ['ent-zrc'] });
    });
  });

  it('surfaces an error if the BE reused the source project_id (no fresh delta — G2 violation)', async () => {
    // a regression that anchored the what-if onto the source project must NOT pass silently.
    deriveWorkMock.mockResolvedValue({ ...sourceWork, project_id: 'src-proj', source_work_id: 'src-id' });
    const onPromoted = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useWhatIfPromotion({ sourceWork, draft: fullDraft, token: 'tok', onPromoted }),
      { wrapper: Wrapper },
    );
    act(() => result.current.promote());
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.error).toMatch(/reused the source project/i);
    expect(onPromoted).not.toHaveBeenCalled();
  });

  it('does not promote without a name (canPromote false) or token', () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useWhatIfPromotion({ sourceWork, draft: { ...fullDraft, name: '  ' }, token: 'tok' }),
      { wrapper: Wrapper },
    );
    expect(result.current.canPromote).toBe(false);
    act(() => result.current.promote());
    expect(deriveWorkMock).not.toHaveBeenCalled();
  });
});
