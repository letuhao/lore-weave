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

// The Row-3 undo captures the chapter's CURRENT predecessor from the book's own order before the
// write (the loaded windows can't see a collapsed arc's chapters).
const books = vi.hoisted(() => ({ listChapters: vi.fn() }));
vi.mock('@/features/books/api', () => ({ booksApi: books }));

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
const patchWindow = vi.fn();

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
        patchWindow,
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
  books.listChapters.mockResolvedValue({ items: [
    { chapter_id: 'book-c1', sort_order: 1 },
    { chapter_id: 'book-c2', sort_order: 2 },
    { chapter_id: 'book-c3', sort_order: 3 },
  ] });
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

describe('optimistic re-place + one-level undo', () => {
  function chapterNode(over: Partial<SummaryNode> & { id: string }): SummaryNode {
    return {
      kind: 'chapter', parent_id: null, structure_node_id: 'arc-a', chapter_id: `book-${over.id}`,
      title: over.id, status: 'draft', version: 1, story_order: 1000, rank: '0m', beat_role: null,
      tension: null, pov_entity_id: null, present_entity_ids: [], present_entity_count: 0, ...over,
    };
  }

  it('Row-1 re-places the card IMMEDIATELY (before the server answers)', () => {
    const { result } = mount({ windowContent: { c1: chapterNode({ id: 'c1' }) } });
    act(() => result.current.moveChapterToArc('c1', 'arc-b'));
    // The card must not sit in its old lane for the round-trip + refetch.
    expect(patchWindow).toHaveBeenCalledWith('c1', { structure_node_id: 'arc-b' });
  });

  it('Row-4 re-parents the scene card immediately', async () => {
    const { result } = mount({ windowContent: { s1: scene({ id: 's1', parent_id: 'ch-1' }) } });
    act(() => result.current.moveSceneToChapter('s1', 'ch-2'));
    expect(patchWindow).toHaveBeenCalledWith('s1', { parent_id: 'ch-2' });
  });

  it('Row-1 undo re-assigns the chapter to the arc it CAME from', async () => {
    const { result } = mount({ windowContent: { c1: chapterNode({ id: 'c1', structure_node_id: 'arc-a' }) } });
    act(() => result.current.moveChapterToArc('c1', 'arc-b'));
    await waitFor(() => expect(result.current.undo).not.toBeNull());
    expect(result.current.undo!.label).toMatch(/chapter/i);

    api.assignChapters.mockClear();
    act(() => result.current.undo!.run());
    await waitFor(() =>
      expect(api.assignChapters).toHaveBeenCalledWith(BOOK, 'arc-a', ['c1'], 'tok'), // back to arc-a
    );
  });

  it('Row-3 undo puts the chapter back after its PRE-MOVE predecessor, read from the book order', async () => {
    // The predecessor cannot come from the loaded windows — the chapter before it may live in a
    // collapsed arc that was never fetched. It is captured from the book's own order before the write.
    const windowContent = { c3: chapterNode({ id: 'c3', story_order: 3000 }) };
    // The book order BEFORE the move: c1, c2, c3 — so c3's predecessor is c2.
    books.listChapters.mockResolvedValueOnce({ items: [
      { chapter_id: 'book-c1', sort_order: 1 },
      { chapter_id: 'book-c2', sort_order: 2 },
      { chapter_id: 'book-c3', sort_order: 3 },
    ] });
    // ...and AFTER it (c3 dragged to the front) — what the undo's own lookup must see.
    books.listChapters.mockResolvedValueOnce({ items: [
      { chapter_id: 'book-c3', sort_order: 1 },
      { chapter_id: 'book-c1', sort_order: 2 },
      { chapter_id: 'book-c2', sort_order: 3 },
    ] });

    const { result } = mount({ windowContent });
    act(() => result.current.reorderChapter('c3', null)); // drag it to the front
    await waitFor(() => expect(result.current.undo).not.toBeNull());

    api.reorderBookChapter.mockClear();
    act(() => result.current.undo!.run());
    await waitFor(() =>
      expect(api.reorderBookChapter).toHaveBeenCalledWith(
        BOOK,
        { chapter_id: 'book-c3', after_chapter_id: 'book-c2' }, // it followed book-c2 before the move
        'tok',
      ),
    );
  });

  it('a NEW move replaces the undo (one level, never a stack)', async () => {
    const { result } = mount({ windowContent: { c1: chapterNode({ id: 'c1' }) } });
    act(() => result.current.moveChapterToArc('c1', 'arc-b'));
    await waitFor(() => expect(result.current.undo).not.toBeNull());
    const first = result.current.undo;

    act(() => result.current.moveChapterToArc('c1', 'arc-c'));
    await waitFor(() => expect(result.current.undo).not.toBe(first));
  });

  it('a FAILED move offers no undo (there is nothing to reverse)', async () => {
    api.assignChapters.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    const { result } = mount({ windowContent: { c1: chapterNode({ id: 'c1' }) } });
    act(() => result.current.moveChapterToArc('c1', 'arc-b'));
    await waitFor(() => expect(result.current.moveError).toBe('boom'));
    expect(result.current.undo).toBeNull();
    // and the optimistic patch is rolled back by the settle reload, not by hand
    expect(reloadWindows).toHaveBeenCalled();
  });
});

describe('Row-3 — the no-op check must use the BOOK order, not the loaded windows', () => {
  it('still moves a chapter whose predecessor lives in a COLLAPSED arc (never a silent no-op)', async () => {
    // Only c3 is loaded (its arc is expanded; c1/c2 sit in a collapsed one). A guard that compared
    // against the loaded windows would see c3 as "already first" and swallow the drag — a silent
    // failure. The real check runs server-side of the decision, against the book's own order.
    books.listChapters.mockResolvedValue({ items: [
      { chapter_id: 'book-c1', sort_order: 1 },
      { chapter_id: 'book-c2', sort_order: 2 },
      { chapter_id: 'book-c3', sort_order: 3 },
    ] });
    const { result } = mount({
      windowContent: {
        c3: {
          kind: 'chapter', id: 'c3', parent_id: null, structure_node_id: 'arc-a',
          chapter_id: 'book-c3', title: 'c3', status: 'draft', version: 1, story_order: 3000,
          rank: '0m', beat_role: null, tension: null, pov_entity_id: null,
          present_entity_ids: [], present_entity_count: 0,
        } as SummaryNode,
      },
    });

    act(() => result.current.reorderChapter('c3', null)); // drag it to the front
    await waitFor(() =>
      expect(api.reorderBookChapter).toHaveBeenCalledWith(
        BOOK, { chapter_id: 'book-c3', after_chapter_id: null }, 'tok',
      ),
    );
  });

  it('a chapter dropped back into the slot it already holds writes nothing', async () => {
    books.listChapters.mockResolvedValue({ items: [
      { chapter_id: 'book-c1', sort_order: 1 },
      { chapter_id: 'book-c2', sort_order: 2 },
    ] });
    const { result } = mount({
      windowContent: {
        c2: {
          kind: 'chapter', id: 'c2', parent_id: null, structure_node_id: 'arc-a',
          chapter_id: 'book-c2', title: 'c2', status: 'draft', version: 1, story_order: 2000,
          rank: '0m', beat_role: null, tension: null, pov_entity_id: null,
          present_entity_ids: [], present_entity_count: 0,
        } as SummaryNode,
        c1: {
          kind: 'chapter', id: 'c1', parent_id: null, structure_node_id: 'arc-a',
          chapter_id: 'book-c1', title: 'c1', status: 'draft', version: 1, story_order: 1000,
          rank: '0m', beat_role: null, tension: null, pov_entity_id: null,
          present_entity_ids: [], present_entity_count: 0,
        } as SummaryNode,
      },
    });

    // c2 already follows c1 — the book order says so, so no write and no undo offered.
    act(() => result.current.reorderChapter('c2', {
      id: 'c1', shape: 'chapter', laneId: 'arc-a', x: 0, y: 0, width: 128,
      collapsed: false, storyOrder: 1000,
    }));
    await waitFor(() => expect(books.listChapters).toHaveBeenCalled());
    expect(api.reorderBookChapter).not.toHaveBeenCalled();
    expect(result.current.undo).toBeNull();
  });
});

describe('Row-3 — the book order must be PAGED (book-service clamps limit to 100)', () => {
  function ch(i: number) {
    return { chapter_id: `book-c${i}`, sort_order: i };
  }
  /**
   * A LIVE 250-chapter book: served in 100-row pages exactly as book-service does, and the reorder
   * endpoint actually permutes it. A static mock would return the pre-move order to the undo's own
   * lookup, so the undo would correctly conclude "already in place" and the test would prove nothing.
   */
  function pagedBook() {
    let order = Array.from({ length: 250 }, (_, k) => `book-c${k + 1}`);
    books.listChapters.mockImplementation((_t: string, _b: string, p: { limit: number; offset: number }) =>
      Promise.resolve({
        items: order
          .map((id, i) => ({ chapter_id: id, sort_order: i + 1 }))
          .slice(p.offset, p.offset + p.limit),
      }),
    );
    api.reorderBookChapter.mockImplementation((_b: string, body: { chapter_id: string; after_chapter_id: string | null }) => {
      const rest = order.filter((id) => id !== body.chapter_id);
      const at = body.after_chapter_id ? rest.indexOf(body.after_chapter_id) + 1 : 0;
      order = [...rest.slice(0, at), body.chapter_id, ...rest.slice(at)];
      return Promise.resolve({ book_id: BOOK, resynced: {} });
    });
    return { at: (i: number) => order[i], indexOf: (id: string) => order.indexOf(id) };
  }
  const node = (id: string, order: number): SummaryNode => ({
    kind: 'chapter', id, parent_id: null, structure_node_id: 'arc-a', chapter_id: `book-${id}`,
    title: id, status: 'draft', version: 1, story_order: order * 1000, rank: '0m', beat_role: null,
    tension: null, pov_entity_id: null, present_entity_ids: [], present_entity_count: 0,
  });

  it('finds a chapter BEYOND the first page, and undoes it to its true predecessor', async () => {
    // The bug: booksApi.listChapters was called with {limit: 500}, which book-service clamps to 100.
    // Chapter 150 was therefore absent from the list ⇒ findIndex -1 ⇒ previous=null ⇒ "it used to be
    // chapter 1" ⇒ clicking Undo moved it to the FRONT OF THE MANUSCRIPT.
    const book = pagedBook();
    const { result } = mount({ windowContent: { c150: node('c150', 150) } });

    act(() => result.current.reorderChapter('c150', null)); // drag it to the front
    await waitFor(() => expect(result.current.undo).not.toBeNull());
    // It PAGED: 250 chapters ⇒ 3 requests (100, 100, 50). A single {limit:500} call would have been
    // clamped to 100 and never seen chapter 150 at all.
    expect(books.listChapters.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(book.indexOf('book-c150')).toBe(0); // it really did move to the front

    act(() => result.current.undo!.run());
    await waitFor(() => expect(book.indexOf('book-c150')).toBe(149)); // back to chapter 150
    expect(book.at(148)).toBe('book-c149');
    expect(book.at(150)).toBe('book-c151'); // and its neighbours are intact
  });

  it('a chapter that is NOT in the book order fails loudly — never silently to position 1', async () => {
    pagedBook();
    const { result } = mount({ windowContent: { gone: node('gone', 9) } }); // book-gone isn't listed
    act(() => result.current.reorderChapter('gone', null));
    await waitFor(() => expect(result.current.moveError).toMatch(/no longer in the book/i));
    expect(api.reorderBookChapter).not.toHaveBeenCalled();
    expect(result.current.undo).toBeNull();
  });
});
