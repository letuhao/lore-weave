import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Work, WorkResolution } from '@/features/composition/types';
import { useLivingWorld, worksFromResolution } from '../useLivingWorld';

// C28 — the hook composes the world's tree from EXISTING endpoints: world books
// (C20) + per-book work resolution (composition). It must collect canon +
// derivatives and join them via the source_work_id chain into this world's books.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const listWorldBooks = vi.fn();
vi.mock('../../api', () => ({
  worldsApi: { listWorldBooks: (...a: unknown[]) => listWorldBooks(...a) },
}));

const resolveWork = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: { resolveWork: (...a: unknown[]) => resolveWork(...a) },
}));

function work(p: Partial<Work> & { id: string; book_id: string }): Work {
  return {
    project_id: p.project_id ?? p.id, user_id: 'u1', book_id: p.book_id, active_template_id: null,
    status: 'active', settings: {}, version: 1, id: p.id,
    source_work_id: p.source_work_id ?? null, branch_point: p.branch_point ?? null,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => vi.clearAllMocks());

describe('worksFromResolution', () => {
  it('collects the marked work plus all candidates', () => {
    const a = work({ id: 'a', book_id: 'b' });
    const c1 = work({ id: 'c1', book_id: 'b' });
    expect(worksFromResolution({ status: 'found', work: a, candidates: [], book_project_id: null, book_project_ids: [] } as WorkResolution)).toEqual([a]);
    expect(worksFromResolution({ status: 'candidates', work: null, candidates: [a, c1], book_project_id: null, book_project_ids: [] } as WorkResolution)).toEqual([a, c1]);
    expect(worksFromResolution(undefined)).toEqual([]);
  });
});

describe('useLivingWorld', () => {
  it('builds canon trunk + dị bản branches from per-book resolutions', async () => {
    listWorldBooks.mockResolvedValue({ items: [{ book_id: 'bookA', title: '万古神帝', description: null, chapter_count: 5 }], total: 1 });
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const d1 = work({ id: 'w-d1', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 2 });
    const d2 = work({ id: 'w-d2', book_id: 'bookA', source_work_id: 'w-canon', branch_point: 4 });
    // a book with canon + 2 derivatives resolves to `candidates` holding all 3.
    resolveWork.mockResolvedValue({ status: 'candidates', work: null, candidates: [canon, d1, d2], book_project_id: null, book_project_ids: [] });

    const { result } = renderHook(() => useLivingWorld('w1'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.tree.trunkCount).toBe(1);
    expect(result.current.tree.branchCount).toBe(2);
    expect(result.current.tree.edges).toHaveLength(2);
  });

  it('does not bleed in another world’s branches (only this world’s books resolved)', async () => {
    listWorldBooks.mockResolvedValue({ items: [{ book_id: 'bookA', title: 'Canon', description: null, chapter_count: 3 }], total: 1 });
    const canon = work({ id: 'w-canon', book_id: 'bookA' });
    const foreign = work({ id: 'w-foreign', book_id: 'bookA', source_work_id: 'w-OTHER', branch_point: 1 });
    resolveWork.mockResolvedValue({ status: 'candidates', work: null, candidates: [canon, foreign], book_project_id: null, book_project_ids: [] });

    const { result } = renderHook(() => useLivingWorld('w1'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const orphan = result.current.tree.nodes.find((n) => n.id === 'w-foreign')!;
    expect(orphan.orphanSource).toBe(true);
    expect(orphan.parentId).toBeNull();
    expect(result.current.tree.edges.some((e) => e.from === 'w-OTHER')).toBe(false);
  });

  it('reports isEmpty when the world has books but no works', async () => {
    listWorldBooks.mockResolvedValue({ items: [{ book_id: 'bookA', title: 'A', description: null, chapter_count: 0 }], total: 1 });
    resolveWork.mockResolvedValue({ status: 'none', work: null, candidates: [], book_project_id: null, book_project_ids: [] });

    const { result } = renderHook(() => useLivingWorld('w1'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isEmpty).toBe(true);
    expect(result.current.tree.nodes).toHaveLength(0);
  });
});
