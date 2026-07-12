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

  it('actual-state fetches PER LOADED CHAPTER once a window opens (lazy, after paint)', async () => {
    api.getChildren.mockResolvedValue({
      items: [
        {
          id: 'ch-node-1', kind: 'chapter', parent_id: null, structure_node_id: 'arc-1',
          chapter_id: 'book-chapter-1', title: 'Ch 1', status: 'outline', version: 1,
          story_order: 1000, rank: 'm', beat_role: null, tension: null, pov_entity_id: null,
          present_entity_ids: [], present_entity_count: 0,
        },
      ],
      next_cursor: null,
    });
    const { result } = renderHook(() => usePlanHub('book-1'), { wrapper });
    await waitFor(() => expect(result.current.layout.lanes.length).toBe(1));

    result.current.toggleArc('arc-1'); // expand ⇒ the chapter window loads
    await waitFor(() => expect(books.listScenes).toHaveBeenCalled());

    // Scoped to THAT chapter — not the whole book.
    expect(books.listScenes).toHaveBeenCalledWith(
      'tok',
      'book-1',
      expect.objectContaining({ chapter_id: 'book-chapter-1' }),
    );
  });
});
