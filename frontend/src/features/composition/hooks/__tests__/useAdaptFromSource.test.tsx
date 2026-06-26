import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import { useAdaptFromSource } from '../useAdaptFromSource';
import type { DerivativeContext } from '../useDerivativeContext';
import { booksApi } from '../../../books/api';

vi.mock('../../../books/api', () => ({
  booksApi: { listChapters: vi.fn(), getDraft: vi.fn() },
}));
const listChapters = vi.mocked(booksApi.listChapters);
const getDraft = vi.mocked(booksApi.getDraft);

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

// Minimal DerivativeContext — the hook only reads isDerivative + branchPoint.
function ctx(over: Partial<DerivativeContext>): DerivativeContext {
  return {
    isDerivative: false, sourceWorkId: null, branchPoint: null, sourceProjectId: null,
    overrideIds: new Set(), overrides: {}, taxonomy: null, povAnchor: null, canonRules: [],
    classify: () => 'inherited', isLoading: false, ...over,
  };
}
const chapters = (items: Array<{ chapter_id: string; sort_order: number }>) =>
  ({ items: items.map((c) => ({ ...c, original_language: 'en' })), total: items.length }) as never;
const draft = (text: string | null) => ({ chapter_id: 'c', body: {}, draft_format: 'html', draft_updated_at: '', draft_version: 1, text_content: text }) as never;

beforeEach(() => vi.clearAllMocks());

describe('useAdaptFromSource (M1 gate)', () => {
  it('no-ops for a greenfield Work (not a derivative) — never fetches', () => {
    const { result } = renderHook(() => useAdaptFromSource('b', 'c1', ctx({ isDerivative: false }), 'tok'), { wrapper: wrapper() });
    expect(result.current.canAdapt).toBe(false);
    expect(result.current.sourceEmpty).toBe(false);
    expect(listChapters).not.toHaveBeenCalled();
    expect(getDraft).not.toHaveBeenCalled();
  });

  it('derivative + chapter AT/AFTER branch + source has prose → canAdapt', async () => {
    listChapters.mockResolvedValue(chapters([{ chapter_id: 'c1', sort_order: 3 }]));
    getDraft.mockResolvedValue(draft('Some inherited source prose.'));
    const { result } = renderHook(
      () => useAdaptFromSource('b', 'c1', ctx({ isDerivative: true, branchPoint: 2 }), 'tok'),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.canAdapt).toBe(true));
    expect(result.current.sourceEmpty).toBe(false);
    expect(getDraft).toHaveBeenCalledWith('tok', 'b', 'c1');
  });

  it('a PRE-branch chapter is NOT adaptable — and never fetches the source draft', async () => {
    listChapters.mockResolvedValue(chapters([{ chapter_id: 'c1', sort_order: 1 }]));
    const { result } = renderHook(
      () => useAdaptFromSource('b', 'c1', ctx({ isDerivative: true, branchPoint: 2 }), 'tok'),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(listChapters).toHaveBeenCalled());
    expect(result.current.canAdapt).toBe(false);
    expect(result.current.sourceEmpty).toBe(false); // pre-branch, not "empty source"
    expect(getDraft).not.toHaveBeenCalled();
  });

  it('at/after branch but EMPTY source draft → sourceEmpty (no action, show hint)', async () => {
    listChapters.mockResolvedValue(chapters([{ chapter_id: 'c1', sort_order: 5 }]));
    getDraft.mockResolvedValue(draft('   ')); // whitespace-only counts as empty
    const { result } = renderHook(
      () => useAdaptFromSource('b', 'c1', ctx({ isDerivative: true, branchPoint: 2 }), 'tok'),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.sourceEmpty).toBe(true));
    expect(result.current.canAdapt).toBe(false);
  });

  it('a "diverge from start" derivative (branch_point null) adapts ANY chapter with prose — no sort fetch', async () => {
    // /review-impl HIGH: branch_point === null = no inherited canon → every source
    // scene is post-branch and adaptable. The BE mirrors this (its exclusion only fires
    // when branch_point is not None). The FE must not hide adapt for from-start branches.
    getDraft.mockResolvedValue(draft('Inherited prose from chapter zero.'));
    const { result } = renderHook(
      () => useAdaptFromSource('b', 'c1', ctx({ isDerivative: true, branchPoint: null }), 'tok'),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.canAdapt).toBe(true));
    expect(listChapters).not.toHaveBeenCalled(); // no reading-order comparison needed
    expect(getDraft).toHaveBeenCalledWith('tok', 'b', 'c1');
  });

  it('a 404 / errored source draft also reads as sourceEmpty (not a silent canAdapt)', async () => {
    listChapters.mockResolvedValue(chapters([{ chapter_id: 'c1', sort_order: 5 }]));
    getDraft.mockRejectedValue(new Error('404'));
    const { result } = renderHook(
      () => useAdaptFromSource('b', 'c1', ctx({ isDerivative: true, branchPoint: 2 }), 'tok'),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.sourceEmpty).toBe(true));
    expect(result.current.canAdapt).toBe(false);
  });
});
