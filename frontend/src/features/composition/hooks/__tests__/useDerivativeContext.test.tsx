import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import {
  classifyGroundingLayer,
  derivativeOverridesKey,
  useDerivativeContext,
} from '../useDerivativeContext';
import type { Work } from '../../types';

const greenfield: Work = {
  project_id: 'p1', user_id: 'u', book_id: 'b', active_template_id: null,
  status: 'active', settings: {}, version: 1,
};
const derivative: Work = { ...greenfield, project_id: 'deriv', source_work_id: 'srcwork', branch_point: 2 };

function wrapperWith(seed?: (qc: QueryClient) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  seed?.(qc);
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return Wrapper;
}

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
  it('no-ops for a greenfield Work (not a derivative)', () => {
    const { result } = renderHook(() => useDerivativeContext(greenfield), { wrapper: wrapperWith() });
    expect(result.current.isDerivative).toBe(false);
    expect(result.current.overrideIds.size).toBe(0);
    expect(result.current.classify('any')).toBe('inherited');
  });

  it('a derivative surfaces source_work_id + branch_point + reads the REAL stashed override set', () => {
    const Wrapper = wrapperWith((qc) =>
      qc.setQueryData(derivativeOverridesKey('deriv'), { sourceProjectId: 'src', overrideIds: ['e1'] }),
    );
    const { result } = renderHook(() => useDerivativeContext(derivative), { wrapper: Wrapper });
    expect(result.current.isDerivative).toBe(true);
    expect(result.current.sourceWorkId).toBe('srcwork');
    expect(result.current.branchPoint).toBe(2);
    expect(result.current.sourceProjectId).toBe('src');
    expect(result.current.classify('e1')).toBe('overridden');
    expect(result.current.classify('e2')).toBe('inherited');
  });
});
