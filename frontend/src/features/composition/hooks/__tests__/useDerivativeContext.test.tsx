import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import {
  classifyGroundingLayer,
  useDerivativeContext,
} from '../useDerivativeContext';
import { compositionApi } from '../../api';
import type { DerivativeContextResponse, Work } from '../../types';

vi.mock('../../api', () => ({ compositionApi: { getDerivativeContext: vi.fn() } }));
const getCtx = vi.mocked(compositionApi.getDerivativeContext);

const greenfield: Work = {
  project_id: 'p1', user_id: 'u', book_id: 'b', active_template_id: null,
  status: 'active', settings: {}, version: 1,
};
const derivative: Work = { ...greenfield, project_id: 'deriv', source_work_id: 'srcwork', branch_point: 2 };

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('classifyGroundingLayer (G2 — INHERITED base vs OVERRIDDEN delta)', () => {
  it('an entity in the override set is OVERRIDDEN; otherwise INHERITED', () => {
    const set = new Set(['e-overridden']);
    expect(classifyGroundingLayer('e-overridden', set)).toBe('overridden');
    expect(classifyGroundingLayer('e-base', set)).toBe('inherited');
  });
  it('an OVERRIDDEN entity is NEVER classified INHERITED', () => {
    const set = new Set(['e1']);
    expect(classifyGroundingLayer('e1', set)).not.toBe('inherited');
  });
});

describe('useDerivativeContext', () => {
  it('no-ops for a greenfield Work (not a derivative) — never fetches', () => {
    const { result } = renderHook(() => useDerivativeContext(greenfield, 'tok'), { wrapper: wrapper() });
    expect(result.current.isDerivative).toBe(false);
    expect(result.current.overrideIds.size).toBe(0);
    expect(result.current.classify('any')).toBe('inherited');
    expect(getCtx).not.toHaveBeenCalled();
  });

  it('a derivative reads the DURABLE spec from the endpoint (overrides keyed by glossary anchor + spec fields)', async () => {
    const resp: DerivativeContextResponse = {
      is_derivative: true,
      source_work_id: 'srcwork',
      source_project_id: 'src',
      branch_point: 2,
      taxonomy: 'pov_shift',
      pov_anchor: 'pov-1',
      canon_rules: ['The hero dies'],
      overrides: [{ target_entity_id: 'g1', overridden_fields: { description: 'now a woman' } }],
    };
    getCtx.mockResolvedValue(resp);
    const { result } = renderHook(() => useDerivativeContext(derivative, 'tok'), { wrapper: wrapper() });
    expect(result.current.isDerivative).toBe(true);
    expect(result.current.sourceWorkId).toBe('srcwork');
    await waitFor(() => expect(result.current.sourceProjectId).toBe('src'));
    expect(getCtx).toHaveBeenCalledWith('deriv', 'tok');
    expect(result.current.branchPoint).toBe(2);
    expect(result.current.taxonomy).toBe('pov_shift');
    expect(result.current.povAnchor).toBe('pov-1');
    expect(result.current.canonRules).toEqual(['The hero dies']);
    // classify keys on the GLOSSARY anchor id, not a knowledge node id
    expect(result.current.classify('g1')).toBe('overridden');
    expect(result.current.classify('node-1')).toBe('inherited');
    expect(result.current.overrides.g1).toEqual({ description: 'now a woman' });
  });
});
