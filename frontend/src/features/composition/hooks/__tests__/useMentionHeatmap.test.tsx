import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMentionHeatmap } from '../useMentionHeatmap';

const { listEntities } = vi.hoisted(() => ({ listEntities: vi.fn() }));
vi.mock('@/features/knowledge/api', () => ({ knowledgeApi: { listEntities } }));

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => listEntities.mockReset());

describe('useMentionHeatmap (T5.2)', () => {
  it('ranks by mention_count and buckets into 0..4 bands by ratio to the max', async () => {
    listEntities.mockResolvedValue({ entities: [
      { id: 'a', canonical_name: 'Kael', name: 'Kael', mention_count: 100, aliases: ['the knight'] },
      { id: 'b', canonical_name: 'Mira', name: 'Mira', mention_count: 50 },
      { id: 'c', canonical_name: 'Tam', name: 'Tam', mention_count: 5 },
    ] });
    const { result } = renderHook(() => useMentionHeatmap('p1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    const d = result.current.data!;
    expect(d.map((h) => h.band)).toEqual([4, 2, 0]); // 100/100→4, 50/100→2, 5/100→0
    expect(d[0]).toMatchObject({ id: 'a', name: 'Kael', mention_count: 100 });
  });

  it('exposes aliases for tinting (excluding the canonical name; missing → [])', async () => {
    listEntities.mockResolvedValue({ entities: [
      { id: 'a', canonical_name: 'Kael', name: 'Kael', mention_count: 10, aliases: ['Kael', 'the knight', ''] },
      { id: 'b', canonical_name: 'Mira', name: 'Mira', mention_count: 5 },
    ] });
    const { result } = renderHook(() => useMentionHeatmap('p1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    const [kael, mira] = result.current.data!;
    expect(kael.aliases).toEqual(['the knight']); // self + empty filtered out
    expect(mira.aliases).toEqual([]); // no aliases field → []
  });

  it('drops entities with zero mentions', async () => {
    listEntities.mockResolvedValue({ entities: [
      { id: 'a', canonical_name: 'Kael', name: 'Kael', mention_count: 10 },
      { id: 'z', canonical_name: 'Ghost', name: 'Ghost', mention_count: 0 },
    ] });
    const { result } = renderHook(() => useMentionHeatmap('p1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data!.map((h) => h.id)).toEqual(['a']);
  });

  it('requests sort_by=mention_count', async () => {
    listEntities.mockResolvedValue({ entities: [] });
    renderHook(() => useMentionHeatmap('p1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(listEntities).toHaveBeenCalled());
    expect(listEntities).toHaveBeenCalledWith(
      expect.objectContaining({ project_id: 'p1', sort_by: 'mention_count' }), 't');
  });

  it('is disabled without a projectId', () => {
    renderHook(() => useMentionHeatmap(undefined, 't'), { wrapper: makeWrapper() });
    expect(listEntities).not.toHaveBeenCalled();
  });
});
