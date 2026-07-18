// 22-C3 controller test: loads the selected node, OCC-patches, and on a 412 reloads the fresh
// node so the next edit lands (the SceneRail recovery contract).
import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OutlineNode, WorkResolution } from '@/features/composition/types';

const getNode = vi.fn();
const patchNode = vi.fn();
let activeSceneId: string | undefined;
let workData: WorkResolution;

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: () => ({ data: workData, isLoading: false }),
}));
vi.mock('@/features/composition/api', () => ({
  compositionApi: {
    getNode: (...a: unknown[]) => getNode(...a),
    patchNode: (...a: unknown[]) => patchNode(...a),
  },
}));
// eslint-disable-next-line @typescript-eslint/no-explicit-any
vi.mock('../../host/StudioHostProvider', () => ({ useStudioBusSelector: (sel: any) => sel({ activeSceneId }) }));

import { useSceneInspector } from '../useSceneInspector';

const node = (o: Partial<OutlineNode> = {}): OutlineNode => ({
  id: 'n1', project_id: 'p1', parent_id: null, kind: 'scene', rank: 'a', title: 'T', chapter_id: 'c',
  story_order: 0, status: 'outline', synopsis: '', version: 3, is_archived: false, beat_role: null, ...o,
});
const found: WorkResolution = {
  status: 'found', work: { project_id: 'p1' } as WorkResolution['work'], candidates: [],
  book_project_id: 'p1', book_project_ids: ['p1'],
};

beforeEach(() => { getNode.mockReset(); patchNode.mockReset(); activeSceneId = 'n1'; workData = found; });

describe('useSceneInspector', () => {
  it('loads the selected node once the Work resolves', async () => {
    getNode.mockResolvedValue(node({ title: 'Loaded' }));
    const { result } = renderHook(() => useSceneInspector('book-1'));
    await waitFor(() => expect(result.current.node?.title).toBe('Loaded'));
    expect(getNode).toHaveBeenCalledWith('n1', 'tok'); // BARE node path — no project prefix
  });

  it('does not load when nothing is selected', async () => {
    activeSceneId = undefined;
    const { result } = renderHook(() => useSceneInspector('book-1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getNode).not.toHaveBeenCalled();
    expect(result.current.node).toBeNull();
  });

  it('patch writes with the OCC version and adopts the returned node', async () => {
    getNode.mockResolvedValue(node({ version: 3 }));
    patchNode.mockResolvedValue(node({ title: 'Renamed', version: 4 }));
    const { result } = renderHook(() => useSceneInspector('book-1'));
    await waitFor(() => expect(result.current.node).not.toBeNull());
    await act(async () => { await result.current.patch({ title: 'Renamed' }); });
    expect(patchNode).toHaveBeenCalledWith('n1', { title: 'Renamed' }, 'tok', 3);
    expect(result.current.node?.version).toBe(4);
  });

  it('a 412 conflict sends the OCC version, surfaces the conflict, and reloads the fresh node', async () => {
    let ver = 3;
    getNode.mockImplementation(async () => node({ version: ver }));
    patchNode.mockRejectedValue(Object.assign(new Error('stale'), { status: 412 }));
    const { result } = renderHook(() => useSceneInspector('book-1'));
    await waitFor(() => expect(result.current.node?.version).toBe(3));
    ver = 9; // the server now holds a fresher version
    await act(async () => { await result.current.patch({ title: 'x' }); });
    expect(patchNode).toHaveBeenCalledWith('n1', { title: 'x' }, 'tok', 3); // OCC If-Match version
    expect(result.current.error).toMatch(/changed elsewhere/);
    await waitFor(() => expect(result.current.node?.version).toBe(9)); // reloaded fresh (inline reload)
  });

  it('serializes rapid back-to-back edits so the 2nd sees the version the 1st bumped (no self-412 drop)', async () => {
    // review fix: EntityRefField commits on every change; two Cast&Setting edits within one round-trip
    // must chain against fresh versions instead of both sending If-Match v3 (which dropped the 2nd).
    getNode.mockResolvedValue(node({ version: 3 }));
    patchNode.mockImplementation(async (_id: string, p: Partial<OutlineNode>, _tok: string, ver: number) => node({ ...p, version: ver + 1 }));
    const { result } = renderHook(() => useSceneInspector('book-1'));
    await waitFor(() => expect(result.current.node?.version).toBe(3));
    await act(async () => {
      const p1 = result.current.patch({ pov_entity_id: 'X' });
      const p2 = result.current.patch({ location_entity_id: 'Y' }); // fired before p1 resolves
      await Promise.all([p1, p2]);
    });
    expect(patchNode).toHaveBeenNthCalledWith(1, 'n1', { pov_entity_id: 'X' }, 'tok', 3);
    expect(patchNode).toHaveBeenNthCalledWith(2, 'n1', { location_entity_id: 'Y' }, 'tok', 4); // saw v4, not stale v3
    expect(result.current.node?.version).toBe(5); // both edits landed, no drop, no false conflict
    expect(result.current.error).toBeNull();
  });

  it('a non-412 save error is surfaced without a version claim', async () => {
    getNode.mockResolvedValue(node({ version: 3 }));
    patchNode.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    const { result } = renderHook(() => useSceneInspector('book-1'));
    await waitFor(() => expect(result.current.node?.version).toBe(3));
    await act(async () => { await result.current.patch({ title: 'x' }); });
    expect(result.current.error).toMatch(/boom/);
  });
});
