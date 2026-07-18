// 24 PH20 Row-5 — draw / delete a scene-link edge.
//
// This row shipped as backend-only (an enum hardening). The canvas had `nodesConnectable={false}`,
// no `onConnect`, and `createSceneLink` did not exist in the FE api at all — so "Row 5 ships" was
// wrong, and the RUN-STATE drift log says so.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const api = vi.hoisted(() => ({
  createSceneLink: vi.fn(),
  deleteSceneLink: vi.fn(),
  assignChapters: vi.fn(),
  getChildren: vi.fn(),
  moveArc: vi.fn(),
  reorderBookChapter: vi.fn(),
  reorderNode: vi.fn(),
}));
vi.mock('../../api', () => api);
vi.mock('@/features/books/api', () => ({ booksApi: { listChapters: vi.fn() } }));

import { usePlanMoves } from '../usePlanMoves';
import type { SummaryNode } from '../../types';

const scene = (id: string): SummaryNode => ({
  id,
  kind: 'scene',
  parent_id: 'ch-1',
  structure_node_id: null,
  chapter_id: 'bc-1',
  title: id,
  status: 'outline',
  version: 1,
  story_order: 1,
  rank: 'm',
  beat_role: null,
  tension: null,
  pov_entity_id: null,
  present_entity_ids: [],
  present_entity_count: 0,
});

const chapter = (id: string): SummaryNode => ({ ...scene(id), kind: 'chapter', parent_id: null });

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function setup(windowContent: Record<string, SummaryNode>) {
  const reloadWindows = vi.fn();
  const hook = renderHook(
    () =>
      usePlanMoves({
        bookId: 'book-1',
        token: 'tok',
        shellNodes: [],
        windowContent,
        reloadWindows,
        patchWindow: vi.fn(),
      }),
    { wrapper },
  );
  return { hook, reloadWindows };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Row-5 linkScenes (PH20)', () => {
  it('creates the edge between two SCENE nodes', async () => {
    api.createSceneLink.mockResolvedValue({ id: 'link-1' });
    const { hook, reloadWindows } = setup({ 's1': scene('s1'), 's2': scene('s2') });

    act(() => hook.result.current.linkScenes('s1', 's2'));

    await waitFor(() => expect(api.createSceneLink).toHaveBeenCalled());
    expect(api.createSceneLink).toHaveBeenCalledWith(
      'book-1',
      { from_node_id: 's1', to_node_id: 's2' },
      'tok',
    );
    // the write settles by RELOADING server truth — the windows are hand-rolled state that
    // invalidateQueries cannot reach.
    await waitFor(() => expect(reloadWindows).toHaveBeenCalled());
  });

  it('REFUSES an endpoint that is not a scene, with a reason', async () => {
    // A stub connector's endpoint is a chapter card / arc rollup standing in for something collapsed
    // (PH13). We don't know WHICH hidden scene was meant, so creating an edge would invent one.
    const { hook } = setup({ 's1': scene('s1'), 'ch-2': chapter('ch-2') });

    act(() => hook.result.current.linkScenes('s1', 'ch-2'));

    expect(api.createSceneLink).not.toHaveBeenCalled();
    expect(hook.result.current.moveError).toMatch(/two scenes/i);
  });

  it('refuses a self-loop', () => {
    const { hook } = setup({ 's1': scene('s1') });
    act(() => hook.result.current.linkScenes('s1', 's1'));
    expect(api.createSceneLink).not.toHaveBeenCalled();
  });

  it('a created link is UNDOABLE — the inverse deletes it', async () => {
    api.createSceneLink.mockResolvedValue({ id: 'link-1' });
    api.deleteSceneLink.mockResolvedValue(undefined);
    const { hook } = setup({ 's1': scene('s1'), 's2': scene('s2') });

    act(() => hook.result.current.linkScenes('s1', 's2'));
    await waitFor(() => expect(hook.result.current.undo).not.toBeNull());

    act(() => hook.result.current.undo!.run());
    await waitFor(() => expect(api.deleteSceneLink).toHaveBeenCalledWith('link-1', 'tok'));
  });

  it('surfaces a duplicate-edge conflict rather than swallowing it', async () => {
    const err = Object.assign(new Error('SCENE_LINK_EXISTS'), { status: 409 });
    api.createSceneLink.mockRejectedValue(err);
    const { hook } = setup({ 's1': scene('s1'), 's2': scene('s2') });

    act(() => hook.result.current.linkScenes('s1', 's2'));
    await waitFor(() => expect(hook.result.current.moveError).toBeTruthy());
  });
});

const edge = (o = {}) => ({
  id: 'link-9',
  from_node_id: 's1',
  to_node_id: 's2',
  kind: 'setup_payoff' as const,
  label: 'the red thread',
  from_chapter_node_id: null,
  to_chapter_node_id: null,
  from_arc_id: null,
  to_arc_id: null,
  ...o,
});

describe('Row-5 unlinkScenes (PH20)', () => {
  it('deletes the edge and reloads', async () => {
    api.deleteSceneLink.mockResolvedValue(undefined);
    const { hook, reloadWindows } = setup({});

    act(() => hook.result.current.unlinkScenes(edge()));

    await waitFor(() => expect(api.deleteSceneLink).toHaveBeenCalledWith('link-9', 'tok'));
    await waitFor(() => expect(reloadWindows).toHaveBeenCalled());
  });

  it('the delete IS undoable - it re-creates the edge with its ORIGINAL kind + label', async () => {
    // An earlier version took only the id and claimed no undo was possible ("the 204 carries no
    // kind/label"). But the CLIENT holds the whole edge, and createSceneLink takes both - so a
    // single click was irreversibly destroying a link for no reason at all.
    api.deleteSceneLink.mockResolvedValue(undefined);
    api.createSceneLink.mockResolvedValue({ id: 'link-new' });
    const { hook } = setup({});

    act(() => hook.result.current.unlinkScenes(edge()));
    await waitFor(() => expect(hook.result.current.undo).not.toBeNull());

    act(() => hook.result.current.undo!.run());
    await waitFor(() =>
      expect(api.createSceneLink).toHaveBeenCalledWith(
        'book-1',
        {
          from_node_id: 's1',
          to_node_id: 's2',
          kind: 'setup_payoff',
          label: 'the red thread', // the label SURVIVES the round trip
        },
        'tok',
      ),
    );
  });
});
