import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { OutlineNode, SceneLink } from '../../types';

// /review-impl MED-1: prove the SHARED-KEY contract with a REAL QueryClient (not a
// mock). useOutline + useSceneLinks share ['composition','outline',pid,false] and
// must dedup to ONE getOutline call, each slicing its half (nodes vs scene_links).
// Mocking the hooks (as the component test does) would never catch a key/select
// drift that double-fetches or returns the wrong slice.
const getOutline = vi.fn();
vi.mock('../../api', () => ({ compositionApi: { getOutline: (...a: unknown[]) => getOutline(...a) } }));

import { useOutline, useSceneLinks } from '../useOutline';

const nodes: OutlineNode[] = [{
  id: 's1', project_id: 'p', parent_id: null, kind: 'scene', rank: 'm', title: 'S1',
  chapter_id: 'C1', story_order: 0, status: 'outline', synopsis: '', version: 1, is_archived: false, beat_role: null,
}];
const scene_links: SceneLink[] = [
  { id: 'l1', project_id: 'p', from_node_id: 's1', to_node_id: 's2', kind: 'setup_payoff', label: '' },
];

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper };
}

beforeEach(() => { getOutline.mockReset(); getOutline.mockResolvedValue({ nodes, scene_links }); });

describe('useOutline + useSceneLinks (T1.3 shared-key)', () => {
  it('issues ONE getOutline and each observer returns its own slice', async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => ({ outline: useOutline('p', 't'), links: useSceneLinks('p', 't') }),
      { wrapper: Wrapper },
    );
    await waitFor(() => {
      expect(result.current.outline.isSuccess).toBe(true);
      expect(result.current.links.isSuccess).toBe(true);
    });
    expect(getOutline).toHaveBeenCalledTimes(1);             // deduped — same query key
    expect(getOutline).toHaveBeenCalledWith('p', 't', false); // default (non-archived) view
    expect(result.current.outline.data).toEqual(nodes);       // nodes slice
    expect(result.current.links.data).toEqual(scene_links);   // scene_links slice
  });

  it('useSceneLinks is disabled without a project id (no fetch)', () => {
    const { Wrapper } = makeWrapper();
    renderHook(() => useSceneLinks(undefined, 't'), { wrapper: Wrapper });
    expect(getOutline).not.toHaveBeenCalled();
  });
});
