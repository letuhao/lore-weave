import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

const getOutline = vi.fn();
const getChapterSceneDrafts = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: {
    getOutline: (...a: unknown[]) => getOutline(...a),
    getChapterSceneDrafts: (...a: unknown[]) => getChapterSceneDrafts(...a),
  },
}));

import { useBranchDiff } from '../useBranchDiff';

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
);

beforeEach(() => {
  getOutline.mockReset();
  getChapterSceneDrafts.mockReset();
});

describe('useBranchDiff', () => {
  it('classifies scenes changed / added / unchanged by (chapter, story_order)', async () => {
    getOutline.mockResolvedValue({
      nodes: [
        { id: 'd0', kind: 'scene', is_archived: false, chapter_id: 'ch1', story_order: 0 },
        { id: 'd1', kind: 'scene', is_archived: false, chapter_id: 'ch1', story_order: 1 },
        { id: 'd2', kind: 'scene', is_archived: false, chapter_id: 'ch1', story_order: 2 },
      ],
      scene_links: [],
    });
    getChapterSceneDrafts.mockImplementation((projectId: string) => {
      if (projectId === 'deriv') {
        return Promise.resolve({ items: [
          { node_id: 'd0', story_order: 0, title: 's0', text: 'same', anchor_node_id: null },        // unchanged (by order)
          { node_id: 'd1', story_order: 1, title: 's1', text: 'branch new', anchor_node_id: null },  // changed (by order)
          { node_id: 'd2', story_order: 2, title: 's2', text: 'all new', anchor_node_id: null },     // added (no canon @2)
        ] });
      }
      return Promise.resolve({ items: [
        { node_id: 'c0', story_order: 0, title: 's0', text: 'same', anchor_node_id: null },
        { node_id: 'c1', story_order: 1, title: 's1', text: 'canon original', anchor_node_id: null },
      ] });
    });

    const { result } = renderHook(() => useBranchDiff('deriv', 'canon', 'tok', true), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const byNode = Object.fromEntries((result.current.data ?? []).map((s) => [s.nodeId, s]));
    expect(byNode.d0.status).toBe('unchanged');
    expect(byNode.d1.status).toBe('changed');
    expect(byNode.d1.canonText).toBe('canon original');
    expect(byNode.d1.branchText).toBe('branch new');
    expect(byNode.d2.status).toBe('added');
    expect(byNode.d2.canonText).toBe('');
  });

  it('pairs by the anchor back-ref (not dense story_order) for a promoted take', async () => {
    // A promoted derivative scene at a FRESH dense story_order (99) that does NOT match
    // its canon counterpart's order (7) — but carries anchor_node_id='c7'. It must pair
    // to canon c7 by the back-ref (a real changed diff), never mis-pair by order.
    getOutline.mockResolvedValue({
      nodes: [{ id: 'dp', kind: 'scene', is_archived: false, chapter_id: 'ch1', story_order: 99 }],
      scene_links: [],
    });
    getChapterSceneDrafts.mockImplementation((projectId: string) =>
      projectId === 'deriv'
        ? Promise.resolve({ items: [{ node_id: 'dp', story_order: 99, title: 'take', text: 'the alternate take', anchor_node_id: 'c7' }] })
        : Promise.resolve({ items: [
            { node_id: 'c99others', story_order: 99, title: 'unrelated', text: 'WRONG pair', anchor_node_id: null },
            { node_id: 'c7', story_order: 7, title: 'anchor', text: 'the canon original', anchor_node_id: null },
          ] }),
    );
    const { result } = renderHook(() => useBranchDiff('deriv', 'canon', 'tok', true), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const s = (result.current.data ?? [])[0];
    expect(s.status).toBe('changed');
    expect(s.canonText).toBe('the canon original');   // paired to c7 by anchor, NOT c99others by order
    expect(s.branchText).toBe('the alternate take');
  });

  it('surfaces a diverged scene with no draft as no-prose (not silently absent)', async () => {
    getOutline.mockResolvedValue({
      nodes: [
        { id: 'dd', kind: 'scene', is_archived: false, chapter_id: 'ch1', story_order: 0 },  // drafted
        { id: 'un', kind: 'scene', is_archived: false, chapter_id: 'ch1', story_order: 1 },  // NO draft
      ],
      scene_links: [],
    });
    getChapterSceneDrafts.mockImplementation((projectId: string) =>
      projectId === 'deriv'
        ? Promise.resolve({ items: [{ node_id: 'dd', story_order: 0, title: 'drafted', text: 'x', anchor_node_id: null }] })
        : Promise.resolve({ items: [] }),
    );
    const { result } = renderHook(() => useBranchDiff('deriv', 'canon', 'tok', true), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const byNode = Object.fromEntries((result.current.data ?? []).map((s) => [s.nodeId, s]));
    expect(byNode.dd.status).toBe('added');    // drafted, no canon counterpart
    expect(byNode.un.status).toBe('no-prose'); // diverged node, no draft yet — surfaced
  });

  it('stays disabled without a source project', () => {
    const { result } = renderHook(() => useBranchDiff('deriv', null, 'tok', true), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(getOutline).not.toHaveBeenCalled();
  });
});
