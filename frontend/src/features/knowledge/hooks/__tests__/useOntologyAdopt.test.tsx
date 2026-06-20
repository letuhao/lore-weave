import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

// The module mock delegates to a per-test `adoptImpl`. A FRESH `vi.fn()` per
// test (not one reused mock with `mockReset` + `mockRejectedValue`) is required
// because vitest tracks the eager rejected promise a reused mock stores; a fresh
// fn per test keeps each rejection scoped to its own test so it never surfaces
// as a stray unhandled rejection in a sibling test.
let adoptImpl: ReturnType<typeof vi.fn>;
vi.mock('../../api/ontology', () => ({
  ontologyApi: { adopt: (...a: unknown[]) => adoptImpl(...a) },
}));

import { useOntologyAdopt } from '../useOntologyAdopt';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  adoptImpl = vi.fn();
});

describe('useOntologyAdopt — M1 adopt-gate', () => {
  it('surfaces needsGlossary state from a 422 NeedsGlossary body', async () => {
    adoptImpl.mockRejectedValue(
      Object.assign(new Error('blocked'), {
        status: 422,
        code: 'KG_ADOPT_NEEDS_GLOSSARY',
        body: {
          code: 'KG_ADOPT_NEEDS_GLOSSARY',
          message: 'missing kinds',
          needs_glossary: { book_id: 'b1', kinds: ['concept', 'technique'] },
        },
      }),
    );

    const { result } = renderHook(() => useOntologyAdopt('p1'), { wrapper });
    await expect(
      result.current.adopt({
        source_schema_id: 'schema-1',
        acknowledge_optional_gaps: false,
      }),
    ).rejects.toThrow('blocked');

    await waitFor(() =>
      expect(result.current.needsGlossary?.needs_glossary.kinds).toEqual([
        'concept',
        'technique',
      ]),
    );
    expect(result.current.needsGlossary?.needs_glossary.book_id).toBe('b1');
    // a 422 gate is NOT a generic error
    expect(result.current.isError).toBe(false);
    expect(adoptImpl).toHaveBeenCalledWith(
      'p1',
      { source_schema_id: 'schema-1', acknowledge_optional_gaps: false },
      'tok',
    );
  });

  it('clears the gate on a subsequent success and exposes the adopted schema', async () => {
    adoptImpl.mockRejectedValueOnce(
      Object.assign(new Error('blocked'), {
        status: 422,
        body: { needs_glossary: { kinds: ['concept'] } },
      }),
    );
    adoptImpl.mockResolvedValueOnce({
      schema_id: 's-new',
      code: 'xianxia',
      scope: 'project',
    });

    const { result } = renderHook(() => useOntologyAdopt('p1'), { wrapper });

    await expect(
      result.current.adopt({ source_schema_id: 'schema-1' }),
    ).rejects.toThrow();
    await waitFor(() => expect(result.current.needsGlossary).not.toBeNull());

    await act(async () => {
      await result.current.adopt({
        source_schema_id: 'schema-1',
        acknowledge_optional_gaps: true,
      });
    });
    await waitFor(() => expect(result.current.needsGlossary).toBeNull());
    expect(result.current.adopted?.schema_id).toBe('s-new');
  });

  it('clearGate dismisses the surfaced blocker', async () => {
    adoptImpl.mockRejectedValue(
      Object.assign(new Error('blocked'), {
        status: 422,
        body: { needs_glossary: { kinds: ['concept'] } },
      }),
    );

    const { result } = renderHook(() => useOntologyAdopt('p1'), { wrapper });
    await expect(
      result.current.adopt({ source_schema_id: 's' }),
    ).rejects.toThrow();
    await waitFor(() => expect(result.current.needsGlossary).not.toBeNull());

    act(() => result.current.clearGate());
    expect(result.current.needsGlossary).toBeNull();
  });

  it('treats a non-422 failure as a generic error (no gate)', async () => {
    adoptImpl.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 500 }),
    );
    const { result } = renderHook(() => useOntologyAdopt('p1'), { wrapper });
    await expect(
      result.current.adopt({ source_schema_id: 's' }),
    ).rejects.toThrow('boom');
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.needsGlossary).toBeNull();
  });
});
