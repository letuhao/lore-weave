// 24 H5 (PH20) — the WRITE controller. These are the decisions the canvas deliberately does NOT
// make: given a drop TARGET, is this a real move, and what are the write's arguments? Everything
// here is a rule the server enforces or a bug we shipped once:
//   • the settle path must reload BOTH the react-query reads AND the hand-rolled windows (the window
//     rows are the ones a move mutates — invalidateQueries cannot reach them);
//   • a scene's append position must come from the SERVER, never from a possibly-unloaded window
//     (after_id=null means "make it FIRST" + renumber, not "append");
//   • an arc's own id must be excluded from the target's children when picking after_id;
//   • a 200 that assigned 0 rows is a silent success, not a success;
//   • the error banner clears when a new move starts.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const api = vi.hoisted(() => ({
  assignChapters: vi.fn(),
  reorderNode: vi.fn(),
  moveArc: vi.fn(),
  getChildren: vi.fn(),
  reorderBookChapter: vi.fn(),
}));
vi.mock('../../api', () => api);

import { usePlanMoves } from '../usePlanMoves';
import type { ArcListNode, SummaryNode } from '../../types';

const BOOK = 'book-1';

function arc(over: Partial<ArcListNode> & { id: string }): ArcListNode {
  return {
    kind: 'arc', parent_id: null, depth: 0, rank: '0m', title: over.id, status: 'draft',
    version: 1, span: null, is_contiguous: true, chapter_count: 0, ...over,
  };
}
function scene(over: Partial<SummaryNode> & { id: string }): SummaryNode {
  return {
    kind: 'scene', parent_id: 'ch-1', structure_node_id: null, chapter_id: 'c-1', title: over.id,
    status: 'draft', version: 3, story_order: 1, rank: '0m', beat_role: null, tension: null,
    pov_entity_id: null, present_entity_ids: [], present_entity_count: 0, ...over,
  };
}

const reloadWindows = vi.fn();

function mount(over: { shellNodes?: ArcListNode[]; windowContent?: Record<string, SummaryNode> } = {}) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return renderHook(
    () =>
      usePlanMoves({
        bookId: BOOK,
        token: 'tok',
        shellNodes: over.shellNodes ?? [],
        windowContent: over.windowContent ?? {},
        reloadWindows,
      }),
    { wrapper },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.assignChapters.mockResolvedValue({ assigned: 1, structure_node_id: 'arc-b' });
  api.reorderNode.mockResolvedValue({ id: 's1', parent_id: 'ch-2', version: 4 });
  api.moveArc.mockResolvedValue({ id: 'arc-x', parent_id: null, depth: 0 });
  api.getChildren.mockResolvedValue({ items: [], next_cursor: null });
  api.reorderBookChapter.mockResolvedValue({ book_id: BOOK, resynced: {} });
});

describe('Row-1 — chapter → arc (assign-chapters)', () => {
  it('rebinds the chapter to the target arc and RELOADS the windows (not just the query cache)', async () => {
    // The shipped bug: the windows are hand-rolled state, so invalidateQueries left the moved card
    // in its OLD lane forever — the write looked silently ignored.
    const { result } = mount();
    act(() => result.current.moveChapterToArc('ch-9', 'arc-b'));
    await waitFor(() => expect(api.assignChapters).toHaveBeenCalledWith(BOOK, 'arc-b', ['ch-9'], 'tok'));
    await waitFor(() => expect(reloadWindows).toHaveBeenCalled());
    expect(result.current.moveError).toBeNull();
  });

  it('a 200 that assigned NOTHING is surfaced as an error (silent success is a bug)', async () => {
    api.assignChapters.mockResolvedValue({ assigned: 0, structure_node_id: 'arc-b' });
    const { result } = mount();
    act(() => result.current.moveChapterToArc('ch-9', 'arc-b'));
    await waitFor(() => expect(result.current.moveError).toMatch(/could not be moved/i));
    expect(reloadWindows).toHaveBeenCalled(); // still re-syncs — the row may have been archived
  });
});

describe('Row-4 — scene → chapter (reorder, OCC)', () => {
  it('asks the SERVER for the target chapter\'s last scene and appends after it, with If-Match', async () => {
    // after_id must be the true last sibling. The target chapter is normally COLLAPSED, so its scene
    // window is empty — trusting it would send after_id=null, which the server reads as "make it the
    // FIRST child" and then renumbers the whole chapter's story_order.
    api.getChildren.mockResolvedValue({
      items: [scene({ id: 's-a', parent_id: 'ch-2', rank: '0m' }), scene({ id: 's-b', parent_id: 'ch-2', rank: '0q' })],
      next_cursor: null,
    });
    const { result } = mount({ windowContent: { s1: scene({ id: 's1', parent_id: 'ch-1', version: 7 }) } });
    act(() => result.current.moveSceneToChapter('s1', 'ch-2'));

    await waitFor(() => expect(api.reorderNode).toHaveBeenCalled());
    expect(api.getChildren).toHaveBeenCalledWith(BOOK, { parentId: 'ch-2' }, expect.objectContaining({ token: 'tok' }));
    expect(api.reorderNode).toHaveBeenCalledWith(
      's1',
      { new_parent_id: 'ch-2', after_id: 's-b' }, // the LAST sibling by rank, from the server
      7, // the scene's version → If-Match
      'tok',
    );
  });

  it('an EMPTY target chapter appends as its first child (after_id null is correct there)', async () => {
    api.getChildren.mockResolvedValue({ items: [], next_cursor: null });
    const { result } = mount({ windowContent: { s1: scene({ id: 's1', parent_id: 'ch-1' }) } });
    act(() => result.current.moveSceneToChapter('s1', 'ch-2'));
    await waitFor(() =>
      expect(api.reorderNode).toHaveBeenCalledWith('s1', { new_parent_id: 'ch-2', after_id: null }, 3, 'tok'),
    );
  });

  it('never counts the MOVED scene as its own predecessor', async () => {
    // Dropping s1 onto a chapter it is already... not in, but which returns s1 in a stale page.
    api.getChildren.mockResolvedValue({
      items: [scene({ id: 's1', parent_id: 'ch-2', rank: '0z' })],
      next_cursor: null,
    });
    const { result } = mount({ windowContent: { s1: scene({ id: 's1', parent_id: 'ch-1' }) } });
    act(() => result.current.moveSceneToChapter('s1', 'ch-2'));
    await waitFor(() =>
      expect(api.reorderNode).toHaveBeenCalledWith('s1', { new_parent_id: 'ch-2', after_id: null }, 3, 'tok'),
    );
  });

  it('dropping a scene back on its OWN chapter writes nothing', () => {
    const { result } = mount({ windowContent: { s1: scene({ id: 's1', parent_id: 'ch-1' }) } });
    act(() => result.current.moveSceneToChapter('s1', 'ch-1'));
    expect(api.reorderNode).not.toHaveBeenCalled();
    expect(api.getChildren).not.toHaveBeenCalled();
  });

  it('a 412 reports the OCC conflict as a RELOAD, never a lost edit', async () => {
    api.reorderNode.mockRejectedValue(Object.assign(new Error('conflict'), { status: 412 }));
    const { result } = mount({ windowContent: { s1: scene({ id: 's1', parent_id: 'ch-1' }) } });
    act(() => result.current.moveSceneToChapter('s1', 'ch-2'));
    await waitFor(() => expect(result.current.moveError).toMatch(/changed elsewhere/i));
    expect(reloadWindows).toHaveBeenCalled(); // the reload IS the recovery the message promises
  });
});

describe('Row-2 — arc band → band (nest vs sibling)', () => {
  const saga = arc({ id: 'saga', kind: 'saga', rank: '0a' });
  const a1 = arc({ id: 'a1', parent_id: 'saga', rank: '0m' });
  const a2 = arc({ id: 'a2', parent_id: 'saga', rank: '0q' });
  const leaf = arc({ id: 'leaf', parent_id: null, rank: '0z' });
  const shell = [saga, a1, a2, leaf];

  it('a drop on a SAGA nests the arc as its last child', async () => {
    const { result } = mount({ shellNodes: shell });
    act(() => result.current.moveArcTo('leaf', 'saga'));
    await waitFor(() =>
      expect(api.moveArc).toHaveBeenCalledWith('leaf', { new_parent_arc_id: 'saga', after_id: 'a2' }, 'tok'),
    );
  });

  it('a drop on a LEAF arc makes the dragged arc that leaf\'s next SIBLING', async () => {
    const { result } = mount({ shellNodes: shell });
    act(() => result.current.moveArcTo('a1', 'leaf'));
    await waitFor(() =>
      expect(api.moveArc).toHaveBeenCalledWith('a1', { new_parent_arc_id: null, after_id: 'leaf' }, 'tok'),
    );
  });

  it('dropping an arc on its OWN parent excludes itself when picking after_id', async () => {
    // a2 is saga's LAST child. Including it would send after_id === a2 — and the server's sibling
    // lookup EXCLUDES the moved node, so after_id wouldn't resolve → a 400 whose message explains
    // the wrong rule entirely ("a saga cannot have a parent…").
    const { result } = mount({ shellNodes: shell });
    act(() => result.current.moveArcTo('a2', 'saga'));
    await waitFor(() =>
      expect(api.moveArc).toHaveBeenCalledWith('a2', { new_parent_arc_id: 'saga', after_id: 'a1' }, 'tok'),
    );
  });

  it('dropping an arc into its OWN subtree (a cycle) never calls the server', () => {
    const { result } = mount({ shellNodes: shell });
    act(() => result.current.moveArcTo('saga', 'a1')); // a1 is saga's child
    expect(api.moveArc).not.toHaveBeenCalled();
  });

  it('dropping an arc on itself is a no-op', () => {
    const { result } = mount({ shellNodes: shell });
    act(() => result.current.moveArcTo('a1', 'a1'));
    expect(api.moveArc).not.toHaveBeenCalled();
  });

  it('a server rejection (cycle / depth>2) surfaces its message', async () => {
    api.moveArc.mockRejectedValue(Object.assign(new Error('STRUCTURE_CONSTRAINT'), { status: 400 }));
    const { result } = mount({ shellNodes: shell });
    act(() => result.current.moveArcTo('leaf', 'saga'));
    await waitFor(() => expect(result.current.moveError).toMatch(/STRUCTURE_CONSTRAINT/));
  });
});

describe('the error banner', () => {
  it('clears when the next move starts (a stale failure must not outlive it)', async () => {
    api.assignChapters.mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 500 }));
    const { result } = mount();
    act(() => result.current.moveChapterToArc('ch-9', 'arc-b'));
    await waitFor(() => expect(result.current.moveError).toBe('boom'));

    act(() => result.current.moveChapterToArc('ch-9', 'arc-b')); // a fresh attempt
    expect(result.current.moveError).toBeNull();
    await waitFor(() => expect(api.assignChapters).toHaveBeenCalledTimes(2));
    expect(result.current.moveError).toBeNull(); // and it stays clear on success
  });
});

describe('Row-3 — chapter → reading order (the MANUSCRIPT move)', () => {
  const unit = (id: string, shape: 'chapter' | 'arc-rollup') =>
    ({ id, shape, laneId: 'A1', x: 0, y: 0, width: 128, collapsed: false, storyOrder: 1000 }) as never;

  function chapter(over: Partial<SummaryNode> & { id: string }): SummaryNode {
    return {
      kind: 'chapter', parent_id: null, structure_node_id: 'A1', chapter_id: `book-${over.id}`,
      title: over.id, status: 'draft', version: 1, story_order: 1000, rank: '0m', beat_role: null,
      tension: null, pov_entity_id: null, present_entity_ids: [], present_entity_count: 0, ...over,
    };
  }
  const windowContent = {
    c1: chapter({ id: 'c1', story_order: 1000 }),
    c2: chapter({ id: 'c2', story_order: 2000 }),
    c3: chapter({ id: 'c3', story_order: 3000 }),
  };

  it('sends the BOOK chapter ids — not the outline node ids', async () => {
    const { result } = mount({ windowContent });
    act(() => result.current.reorderChapter('c1', unit('c2', 'chapter')));
    await waitFor(() =>
      expect(api.reorderBookChapter).toHaveBeenCalledWith(
        BOOK,
        { chapter_id: 'book-c1', after_chapter_id: 'book-c2' }, // book-service speaks chapter_ids
        'tok',
      ),
    );
  });

  it('a drop before everything makes it chapter 1 (after_chapter_id null)', async () => {
    const { result } = mount({ windowContent });
    act(() => result.current.reorderChapter('c3', null));
    await waitFor(() =>
      expect(api.reorderBookChapter).toHaveBeenCalledWith(
        BOOK, { chapter_id: 'book-c3', after_chapter_id: null }, 'tok',
      ),
    );
  });

  it('REFUSES to move a chapter past a collapsed arc — and says why', () => {
    // The rollup hides chapters we never loaded, so "after that arc" cannot be named to the server.
    // Falling back to the last loaded chapter would place this chapter BEFORE the arc's hidden
    // chapters — a silent, wrong move on the real manuscript.
    const { result } = mount({ windowContent });
    act(() => result.current.reorderChapter('c1', unit('A2', 'arc-rollup')));
    expect(api.reorderBookChapter).not.toHaveBeenCalled();
    expect(result.current.moveError).toMatch(/expand that arc/i);
  });

  it('a drop into the slot it already occupies writes nothing', () => {
    const { result } = mount({ windowContent });
    act(() => result.current.reorderChapter('c2', unit('c1', 'chapter'))); // c2 already follows c1
    expect(api.reorderBookChapter).not.toHaveBeenCalled();
  });

  it('reloads the windows on settle — the story_order mirror just changed for EVERY chapter', async () => {
    const { result } = mount({ windowContent });
    act(() => result.current.reorderChapter('c1', unit('c3', 'chapter')));
    await waitFor(() => expect(reloadWindows).toHaveBeenCalled());
  });

  it('surfaces a failed reorder (the manuscript may be reordered but the mirror stale)', async () => {
    api.reorderBookChapter.mockRejectedValue(
      Object.assign(new Error('MIRROR_RESYNC_FAILED'), { status: 502 }),
    );
    const { result } = mount({ windowContent });
    act(() => result.current.reorderChapter('c1', unit('c3', 'chapter')));
    await waitFor(() => expect(result.current.moveError).toMatch(/MIRROR_RESYNC_FAILED/));
  });
});
