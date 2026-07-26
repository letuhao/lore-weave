// 24 H8.1 / PH9 — "the cold-open budget is stated ONCE, and enforced by H8.1: ≤ 5 requests
// (shell + overlay + scene-links + entity names + conformance status) before the lane structure
// paints — chapter/scene windows and actual-state joins load lazily, AFTER paint."
//
// It was VIOLATED. `useActualState` paged the WHOLE book's scene index on mount: on a 10k-chapter
// book that is ~100 sequential requests before the two-truths join can settle, on the one read the
// spec explicitly says should trail the paint.
//
// A budget nobody asserts is a comment. This is the assertion.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const api = vi.hoisted(() => ({
  getArcs: vi.fn(),
  getPlanOverlay: vi.fn(),
  getSceneLinks: vi.fn(),
  getConformanceStatus: vi.fn(),
  getChildren: vi.fn(),
  materializeScenes: vi.fn(),
  assignChapters: vi.fn(),
  moveArc: vi.fn(),
  reorderBookChapter: vi.fn(),
  reorderNode: vi.fn(),
  createSceneLink: vi.fn(),
  deleteSceneLink: vi.fn(),
}));
const books = vi.hoisted(() => ({ listScenes: vi.fn(), listChapters: vi.fn() }));
const glossary = vi.hoisted(() => ({ listEntityNamesWithMeta: vi.fn(), listEntityNames: vi.fn() }));

vi.mock('../../api', () => api);
vi.mock('@/features/books/api', () => ({ booksApi: books }));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: glossary }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

import { usePlanHub } from '../usePlanHub';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  // A book with arcs, all COLLAPSED by default (v1) ⇒ no chapter window loads.
  api.getArcs.mockResolvedValue({
    arcs: [
      {
        id: 'arc-1', kind: 'arc', parent_id: null, depth: 0, rank: 'm', title: 'Arc',
        status: 'active', version: 1, span: null, first_story_order: null,
        is_contiguous: true, chapter_count: 340,
      },
    ],
  });
  api.getPlanOverlay.mockResolvedValue({
    problems: { by_node: {}, refs_capped: false },
    tension_rollup: [], motif_chips: [], unplanned_chapters: [],
  });
  api.getSceneLinks.mockResolvedValue({ scene_links: [] });
  api.getConformanceStatus.mockResolvedValue({ arcs: [], index: { stale_chapter_count: 0 } });
  api.getChildren.mockResolvedValue({ items: [], next_cursor: null });
  glossary.listEntityNamesWithMeta.mockResolvedValue({ items: [], complete: true });
  books.listScenes.mockResolvedValue({ items: [], next_cursor: null });
  books.listChapters.mockResolvedValue({ items: [] });
});

describe('cold-open request budget (H8.1 / PH9)', () => {
  it('issues at most FIVE reads before the lane structure paints', async () => {
    const { result } = renderHook(() => usePlanHub('book-1'), { wrapper });
    await waitFor(() => expect(result.current.layout.lanes.length).toBe(1));

    // The five named surfaces — shell, overlay, scene-links, conformance, entity-names.
    const coldOpen =
      api.getArcs.mock.calls.length +
      api.getPlanOverlay.mock.calls.length +
      api.getSceneLinks.mock.calls.length +
      api.getConformanceStatus.mock.calls.length +
      glossary.listEntityNamesWithMeta.mock.calls.length;
    expect(coldOpen).toBeLessThanOrEqual(5);
    expect(coldOpen).toBe(5); // and it really is all five — none silently dropped

    // …AND nothing ELSE fired. Enumerating the ALLOWED calls but not the FORBIDDEN ones is half a
    // test: it is exactly what let `useBookChapters` re-introduce a ~100-request cold-open walk one
    // commit after A11 removed one, with this suite still green.
    expect(books.listScenes).not.toHaveBeenCalled();
    expect(books.listChapters).not.toHaveBeenCalled();
  });

  it('does NOT walk the chapter spine at cold open (the ⚓ anchor picker is a DRAWER control)', () => {
    renderHook(() => usePlanHub('book-1'), { wrapper });
    // Nothing is selected ⇒ no drawer ⇒ no picker ⇒ no spine walk. It is up to 200 serial requests.
    expect(books.listChapters).not.toHaveBeenCalled();
  });

  it('does NOT page the whole book scene index at cold open (the violation)', async () => {
    const { result } = renderHook(() => usePlanHub('book-1'), { wrapper });
    await waitFor(() => expect(result.current.layout.lanes.length).toBe(1));

    // Every arc is collapsed ⇒ no chapter window is loaded ⇒ NO chapter has actual-state to fetch.
    // The old hook fired a whole-book `listScenes` walk here regardless.
    expect(books.listScenes).not.toHaveBeenCalled();
  });

  it('a collapsed arc loads no chapter window either (PH11)', async () => {
    const { result } = renderHook(() => usePlanHub('book-1'), { wrapper });
    await waitFor(() => expect(result.current.layout.lanes.length).toBe(1));

    // The ONLY children call allowed at cold open is the PH21 unassigned window (arc-less chapters
    // hang off no arc, so no expand gesture could ever reveal them). Never a per-arc chapter page.
    const axes = api.getChildren.mock.calls.map((c) => c[1]);
    expect(axes.every((a) => 'unassigned' in a)).toBe(true);
  });

  it("NEVER reads book-service's scene index — not at cold open, not on expand, not ever", async () => {
    // ── THE AMENDMENT'S PAYOFF, and this test is the proof. ────────────────────────────────────
    //
    // This test used to assert the OPPOSITE: that `useActualState` paged book-service's scene index
    // PER LOADED CHAPTER, lazily, after paint. That read existed to derive "written vs not yet
    // written" client-side, and it cost ~130 lines of machinery — a generation guard against
    // book-switch races, a fetch-dedupe set, per-chapter completeness tracking, a page-walk bound,
    // and an error channel — all of which existed ONLY because the derivation lived where data
    // arrives incrementally, out of order, and can be interrupted.
    //
    // `written` is now MAINTAINED server-side (outline_node.written_scene_id, reconciled from
    // scenes.source_scene_id) and rides the node payload the Hub already fetches. So the read is
    // not merely deferred or scoped — IT IS GONE.
    //
    // The budget test's own header warns that enumerating allowed-but-not-forbidden calls is half a
    // test. This is the forbidden half, and it just got absolute: `listScenes` must never be called.
    api.getChildren.mockResolvedValue({
      items: [
        {
          id: 'ch-node-1', kind: 'chapter', parent_id: null, structure_node_id: 'arc-1',
          chapter_id: 'book-chapter-1', title: 'Ch 1', status: 'outline', version: 1,
          story_order: 1000, rank: 'm', beat_role: null, tension: null, pov_entity_id: null,
          present_entity_ids: [], present_entity_count: 0, written: true,
        },
      ],
      next_cursor: null,
    });
    const { result } = renderHook(() => usePlanHub('book-1'), { wrapper });
    await waitFor(() => expect(result.current.layout.lanes.length).toBe(1));

    result.current.toggleArc('arc-1'); // expand ⇒ the chapter window loads
    await waitFor(() => expect(api.getChildren).toHaveBeenCalled());

    // The expand loaded the window — and STILL no manuscript read.
    expect(books.listScenes).not.toHaveBeenCalled();
    expect(books.listChapters).not.toHaveBeenCalled();
  });

  it('the written verdict comes off the NODE PAYLOAD, with no second source to reconcile', async () => {
    api.getChildren.mockResolvedValue({
      items: [
        {
          id: 'sc-1', kind: 'scene', parent_id: 'ch-node-1', structure_node_id: null,
          chapter_id: 'book-chapter-1', title: 'S1', status: 'empty', version: 1,
          story_order: 1001, rank: 'm', beat_role: null, tension: null, pov_entity_id: null,
          present_entity_ids: [], present_entity_count: 0, written: true,
        },
      ],
      next_cursor: null,
    });
    const { result } = renderHook(() => usePlanHub('book-1'), { wrapper });
    result.current.toggleArc('arc-1');
    await waitFor(() => expect(result.current.unionState['sc-1']).toBe('written'));

    // …and note `status: 'empty'` on that same node. The author has NOT marked it done, but the
    // prose exists. Desired state and actual state, side by side — PH16's two chips, and the reason
    // `written` could never have been folded into `status`.
    expect(books.listScenes).not.toHaveBeenCalled();
  });
});
