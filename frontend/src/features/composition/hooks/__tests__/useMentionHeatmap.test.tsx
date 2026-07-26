import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMentionHeatmap } from '../useMentionHeatmap';

// M7 — the heatmap now reads per-chapter mention_count (glossary chapter-entities)
// windowed to the chapter, merging aliases from glossary known-entities (same id-space).
const { chapterEntities, knownEntitiesAsOf } = vi.hoisted(() => ({
  chapterEntities: vi.fn(),
  knownEntitiesAsOf: vi.fn(),
}));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: { chapterEntities, knownEntitiesAsOf } }));

const ce = (entity_id: string, name: string, mention_count: number) =>
  ({ entity_id, name, kind_code: 'character', relevance: 'major' as const, chapter_index: 0, mention_count });
const ke = (entity_id: string, name: string, aliases: string[]) =>
  ({ entity_id, name, kind_code: 'character', aliases, frequency: 1, first_chapter_index: 0, last_chapter_index: 0, coverage_pct: 0 });

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => { chapterEntities.mockReset(); knownEntitiesAsOf.mockReset(); knownEntitiesAsOf.mockResolvedValue([]); });

describe('useMentionHeatmap (M7 — per-chapter windowed)', () => {
  it('ranks by per-chapter mention_count and bands by ratio to the max', async () => {
    chapterEntities.mockResolvedValue([ce('a', 'Kael', 100), ce('b', 'Mira', 50), ce('c', 'Tam', 5)]);
    const { result } = renderHook(() => useMentionHeatmap('b1', 'c1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data.length).toBe(3));
    expect(result.current.data.map((h) => h.band)).toEqual([4, 2, 0]); // 100/100→4, 50/100→2, 5/100→0
    expect(result.current.data[0]).toMatchObject({ id: 'a', name: 'Kael', mention_count: 100 });
  });

  it('windows on the chapter — calls chapter-entities with bookId + chapterId', async () => {
    chapterEntities.mockResolvedValue([]);
    renderHook(() => useMentionHeatmap('b1', 'c1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(chapterEntities).toHaveBeenCalledWith('b1', 'c1', 't'));
  });

  it('merges aliases from glossary known-entities (same id-space), excluding the canonical name', async () => {
    chapterEntities.mockResolvedValue([ce('a', 'Kael', 10), ce('b', 'Mira', 5)]);
    knownEntitiesAsOf.mockResolvedValue([ke('a', 'Kael', ['Kael', 'the knight', '']), ke('b', 'Mira', [])]);
    const { result } = renderHook(() => useMentionHeatmap('b1', 'c1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data.length).toBe(2));
    const [kael, mira] = result.current.data;
    expect(kael.aliases).toEqual(['the knight']); // self + empty filtered out
    expect(mira.aliases).toEqual([]);
    // whole-book alias lookup (no before_chapter_index window — name forms aren't spoilers)
    expect(knownEntitiesAsOf).toHaveBeenCalledWith('b1', { minFrequency: 1, limit: 500 }, 't');
  });

  it('drops entities with zero per-chapter mentions', async () => {
    chapterEntities.mockResolvedValue([ce('a', 'Kael', 10), ce('z', 'Ghost', 0)]);
    const { result } = renderHook(() => useMentionHeatmap('b1', 'c1', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.data.length).toBe(1));
    expect(result.current.data.map((h) => h.id)).toEqual(['a']);
  });

  it('is disabled without a chapterId (no fetch)', () => {
    renderHook(() => useMentionHeatmap('b1', undefined, 't'), { wrapper: makeWrapper() });
    expect(chapterEntities).not.toHaveBeenCalled();
  });
});
