// S-02 — manuscript parts (acts / volumes) FE client + the pure grouping helper.
//
// This is the frontend seam over book-service's S-02 routes (parts CRUD + the
// move-chapter-to-part route) plus `groupChaptersByParts`, the PURE function that
// turns (parts, chapters) into the two-level tree the manuscript navigator renders:
// each active act as a collapsible group with its chapters nested, followed by an
// "Unassigned" bucket for `part_id IS NULL` (the flat manuscript). See the design
// draft design-drafts/screens/studio/screen-manuscript-parts.html.
//
// Kept SELF-CONTAINED (its own file, its own types) on purpose: the navigator's
// row renderer + the wiring into useManuscriptTree live in ManuscriptNavigator.tsx
// / useManuscriptTree.ts, which are being edited by a concurrent session. This file
// is the tested building block that wiring consumes — it does NOT widen the shared
// ManuscriptRowKind union (that would risk the FE build for every session).

import { apiJson } from '@/api';
import type { Chapter } from '@/features/books/api';

/** A manuscript part (act / volume) — book-service `parts` row. */
export interface Part {
  part_id: string;
  book_id: string;
  title: string | null;
  path: string;
  sort_order: number;
  lifecycle_state: 'active' | 'trashed';
  created_at?: string | null;
  updated_at?: string | null;
}

interface PartsListResponse {
  items: Part[];
}

/**
 * The parts client. Every route is grant-gated server-side (VIEW to list, EDIT to
 * write) — the FE only gates the affordance's visibility on the book's access_level,
 * it never re-implements the check. Move/un-home go through the dedicated
 * chapters/{id}/part route, NOT patchChapter (keeps patchChapter's OCC untouched).
 */
export const partsApi = {
  /** GET — active parts in sort order (include_trashed adds soft-trashed ones for a restore UI). */
  list(token: string, bookId: string, opts: { includeTrashed?: boolean } = {}): Promise<PartsListResponse> {
    const q = opts.includeTrashed ? '?include_trashed=true' : '';
    return apiJson<PartsListResponse>(`/v1/books/${bookId}/parts${q}`, { token });
  },

  /** POST — create an act (appended at the end). 201. */
  create(token: string, bookId: string, title: string): Promise<Part> {
    return apiJson<Part>(`/v1/books/${bookId}/parts`, {
      method: 'POST',
      token,
      body: JSON.stringify({ title }),
    });
  },

  /** PATCH — rename an act (last-write-wins, no OCC). */
  rename(token: string, bookId: string, partId: string, title: string): Promise<Part> {
    return apiJson<Part>(`/v1/books/${bookId}/parts/${partId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify({ title }),
    });
  },

  /** POST /reorder — orderedIds must be EXACTLY the book's active parts in the new order. */
  reorder(token: string, bookId: string, orderedIds: string[]): Promise<PartsListResponse> {
    return apiJson<PartsListResponse>(`/v1/books/${bookId}/parts/reorder`, {
      method: 'POST',
      token,
      body: JSON.stringify({ ordered_ids: orderedIds }),
    });
  },

  /** DELETE — soft-trash an act; its chapters are UN-HOMED (part_id→NULL), never deleted. 204. */
  archive(token: string, bookId: string, partId: string): Promise<void> {
    return apiJson<void>(`/v1/books/${bookId}/parts/${partId}`, { method: 'DELETE', token });
  },

  /** POST /restore — restore a trashed act (does NOT re-home its former chapters). */
  restore(token: string, bookId: string, partId: string): Promise<Part> {
    return apiJson<Part>(`/v1/books/${bookId}/parts/${partId}/restore`, { method: 'POST', token });
  },

  /**
   * PATCH .../chapters/{id}/part — move a chapter into an act (partId), or un-home it
   * into the flat manuscript (partId = null). The dedicated move route, separate from
   * patchChapter. Returns the updated chapter (echoing its new part_id).
   */
  setChapterPart(token: string, bookId: string, chapterId: string, partId: string | null): Promise<Chapter> {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}/part`, {
      method: 'PATCH',
      token,
      body: JSON.stringify({ part_id: partId }),
    });
  },
};

// ── Pure grouping — (parts, chapters) → the two-level navigator model ─────────

/** The minimal chapter shape the grouping needs (a subset of books/api Chapter). */
export interface ChapterLike {
  chapter_id: string;
  title?: string | null;
  original_filename?: string;
  sort_order: number;
  part_id?: string | null;
}

/** A rendered group: an act (or the synthetic "unassigned" bucket) + its chapters. */
export interface PartGroup {
  /** The part id, or null for the synthetic Unassigned bucket. */
  partId: string | null;
  title: string | null;
  /** true only for the Unassigned bucket (styled + non-editable — it is not a real act). */
  unassigned: boolean;
  chapters: ChapterLike[];
}

/** Options for the "empty flat book" case — see groupChaptersByParts. */
export interface GroupOptions {
  /** Always emit the Unassigned bucket even when empty (so an empty flat book still
   *  shows the drop target). Default false: hide an empty Unassigned bucket. */
  alwaysShowUnassigned?: boolean;
}

/**
 * groupChaptersByParts — the pure model the navigator's flat branch renders.
 *
 * Rules (mirroring screen-manuscript-parts.html + the S-02 spec):
 *   - Active parts appear in sort_order, each with the chapters whose part_id points
 *     at it (chapters within a group keep their own sort_order order).
 *   - Chapters with a null/undefined part_id — OR a part_id that matches no ACTIVE
 *     part (e.g. its act was trashed, which un-homes lazily / a stale row) — fall into
 *     the trailing "Unassigned" bucket, so no chapter is ever dropped from the view.
 *   - The Unassigned bucket is emitted only when it has chapters, unless
 *     alwaysShowUnassigned is set (an empty flat book still needs a drop target).
 *   - An empty act still renders (an act with no chapters is valid — you just made it).
 *
 * Pure + deterministic ⇒ unit-testable without a DB or a component.
 */
export function groupChaptersByParts(
  parts: Part[],
  chapters: ChapterLike[],
  opts: GroupOptions = {},
): PartGroup[] {
  const active = parts
    .filter((p) => p.lifecycle_state === 'active')
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order);
  const activeIds = new Set(active.map((p) => p.part_id));

  const byPart = new Map<string, ChapterLike[]>();
  const unassigned: ChapterLike[] = [];
  for (const ch of chapters) {
    const pid = ch.part_id;
    if (pid && activeIds.has(pid)) {
      const bucket = byPart.get(pid);
      if (bucket) bucket.push(ch);
      else byPart.set(pid, [ch]);
    } else {
      unassigned.push(ch);
    }
  }

  const sortByOrder = (list: ChapterLike[]) => list.slice().sort((a, b) => a.sort_order - b.sort_order);

  const groups: PartGroup[] = active.map((p) => ({
    partId: p.part_id,
    title: p.title,
    unassigned: false,
    chapters: sortByOrder(byPart.get(p.part_id) ?? []),
  }));

  if (unassigned.length > 0 || opts.alwaysShowUnassigned) {
    groups.push({ partId: null, title: null, unassigned: true, chapters: sortByOrder(unassigned) });
  }
  return groups;
}
