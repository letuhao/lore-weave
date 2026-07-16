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
          { node_id: 'd0', story_order: 0, title: 's0', text: 'same' },        // unchanged
          { node_id: 'd1', story_order: 1, title: 's1', text: 'branch new' },  // changed
          { node_id: 'd2', story_order: 2, title: 's2', text: 'all new' },     // added (no canon @2)
        ] });
      }
      return Promise.resolve({ items: [
        { node_id: 'c0', story_order: 0, title: 's0', text: 'same' },
        { node_id: 'c1', story_order: 1, title: 's1', text: 'canon original' },
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

  it('stays disabled without a source project', () => {
    const { result } = renderHook(() => useBranchDiff('deriv', null, 'tok', true), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(getOutline).not.toHaveBeenCalled();
  });
});
