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
let adoptPreviewImpl: ReturnType<typeof vi.fn>;
vi.mock('../../api/ontology', () => ({
  ontologyApi: {
    adopt: (...a: unknown[]) => adoptImpl(...a),
    adoptPreview: (...a: unknown[]) => adoptPreviewImpl(...a),
  },
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
  adoptPreviewImpl = vi.fn().mockResolvedValue({ has_current: false, would_lose: [] });
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

describe('useOntologyAdopt — re-adopt loss preview (D-KG-LC-REVADOPT-LOSS)', () => {
  it('does not fetch a preview until a template is selected', async () => {
    renderHook(() => useOntologyAdopt('p1'), { wrapper });
    // no selection => query disabled => no call.
    await new Promise((r) => setTimeout(r, 0));
    expect(adoptPreviewImpl).not.toHaveBeenCalled();
  });

  it('auto-fetches the preview on selection and exposes the losses', async () => {
    adoptPreviewImpl.mockResolvedValue({
      has_current: true,
      would_lose: [{ node_type: 'edge_type', code: 'CUSTOM', change: 'removed_upstream' }],
    });
    const { result } = renderHook(() => useOntologyAdopt('p1', 's1'), { wrapper });

    await waitFor(() => expect(result.current.hasLoss).toBe(true));
    expect(adoptPreviewImpl).toHaveBeenCalledWith(
      'p1',
      { source_schema_id: 's1' },
      'tok',
    );
    expect(result.current.wouldLose).toHaveLength(1);
    // adopt stays gated until the user acknowledges.
    expect(result.current.lossBlocked).toBe(true);
  });

  it('clears lossBlocked after acknowledgeLoss', async () => {
    adoptPreviewImpl.mockResolvedValue({
      has_current: true,
      would_lose: [{ node_type: 'edge_type', code: 'CUSTOM', change: 'removed_upstream' }],
    });
    const { result } = renderHook(() => useOntologyAdopt('p1', 's1'), { wrapper });
    await waitFor(() => expect(result.current.lossBlocked).toBe(true));

    act(() => result.current.acknowledgeLoss());
    await waitFor(() => expect(result.current.lossBlocked).toBe(false));
    // the warning data is still present — only the gate is lifted.
    expect(result.current.hasLoss).toBe(true);
  });

  it('does not block when the project has no current schema', async () => {
    adoptPreviewImpl.mockResolvedValue({ has_current: false, would_lose: [] });
    const { result } = renderHook(() => useOntologyAdopt('p1', 's1'), { wrapper });
    await waitFor(() => expect(adoptPreviewImpl).toHaveBeenCalled());
    expect(result.current.hasLoss).toBe(false);
    expect(result.current.lossBlocked).toBe(false);
  });

  it('re-arms the gate when a different template is selected', async () => {
    adoptPreviewImpl.mockResolvedValue({
      has_current: true,
      would_lose: [{ node_type: 'edge_type', code: 'CUSTOM', change: 'removed_upstream' }],
    });
    const { result, rerender } = renderHook(
      ({ sel }) => useOntologyAdopt('p1', sel),
      { wrapper, initialProps: { sel: 's1' } },
    );
    await waitFor(() => expect(result.current.lossBlocked).toBe(true));
    act(() => result.current.acknowledgeLoss());
    await waitFor(() => expect(result.current.lossBlocked).toBe(false));

    // pick a different template — the prior ack no longer matches → re-armed.
    rerender({ sel: 's2' });
    await waitFor(() => expect(result.current.lossBlocked).toBe(true));
  });
});
