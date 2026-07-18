// 22 §GUI — the scene-browser list is a UNION over the source map, not one table. This is
// the pure, headless-testable core of that union (the view just renders the rows). "Scene" is
// split across two services joined only by `scenes.source_scene_id → outline_node.id` (SC2, the
// INVERTED anchor), so a scene has TWO independent truths and THREE possible row shapes:
//
//   linked      index row (book-service Scene) + spec row (composition OutlineNode) joined  → normal
//   spec_only   a kind='scene' OutlineNode no index row points at                            → "not yet written"
//   index_only  a Scene with source_scene_id NULL (or dangling)                              → "written, not decompiled" / anchor lost
//
// A book whose spec was never decompiled (SC6) renders entirely as index_only — exactly what
// "browse a binary without its source" looks like. Rendering both failure modes (BPS-13) is the
// point; hiding either blurs the seam the architecture exists to enforce.
import type { Scene } from '@/features/books/api';
import type { OutlineNode } from '@/features/composition/types';

export type SceneRowShape = 'linked' | 'spec_only' | 'index_only';

export type SceneUnionRow = {
  shape: SceneRowShape;
  // Stable key for React + selection. Prefer the spec node id (the authored identity); fall
  // back to the index scene id for an index_only row that has no spec node.
  key: string;
  index: Scene | null; // book-service identity (leaf_text, parse title, anchor state)
  spec: OutlineNode | null; // composition intent (status, pov, tension, goal, craft…)
  // Convenience derivations the table renders; kept here so the classification and the
  // display agree (one source of truth for "which chapter / order is this row").
  chapterId: string | null;
  sortOrder: number | null;
  anchorLost: boolean; // index_only where a source_scene_id was set but resolves to nothing
};

/**
 * Join the book-service scene index with the composition spec into ordered union rows.
 *
 * Precedence for a Scene whose `source_scene_id` is set:
 *   - resolves to a live spec node  → `linked`
 *   - set but resolves to nothing   → `index_only` + `anchorLost` (a dangling back-link, IX-5 read-time orphan)
 *   - null                          → `index_only` (never decompiled)
 * Every kind='scene' spec node NOT claimed by a linked index row is emitted as `spec_only`.
 *
 * `specNodes` may include non-scene kinds (whole-outline reads) — only kind='scene', non-archived
 * nodes participate. Ordering: by (chapterId, sortOrder) with nulls last, stable by key.
 *
 * `specComplete` (default true) gates the `spec_only` pass. The spec side is loaded WHOLE, but the
 * index side is keyset-paged — so until every index page is loaded, an unclaimed scene spec may be
 * "unclaimed" only because its index scene is on a not-yet-loaded page, NOT because it is unwritten.
 * Emitting it as spec_only then would falsely label a written+decompiled scene "not yet written"
 * (the majority of a >100-scene book on first open). So the caller passes `specComplete=false` while
 * more index pages remain; spec_only rows appear once the index is fully loaded. (Windowed spec
 * paging — showing planned-unwritten scenes per-chapter mid-scroll — is the C2b follow-up.)
 */
export function joinSceneRows(
  scenes: Scene[], specNodes: OutlineNode[], specComplete = true,
): SceneUnionRow[] {
  const sceneSpecs = specNodes.filter((n) => n.kind === 'scene' && !n.is_archived);
  const specById = new Map<string, OutlineNode>(sceneSpecs.map((n) => [n.id, n]));
  const claimedSpecIds = new Set<string>();
  const rows: SceneUnionRow[] = [];

  for (const s of scenes) {
    const linkedSpec = s.source_scene_id ? specById.get(s.source_scene_id) ?? null : null;
    // A spec node already claimed by an earlier scene means TWO index rows point at one spec — a
    // genuine anomaly (source_scene_id is a non-unique soft ref; a duplicated anchor heading yields
    // it). Surface the second as an anchor-lost index_only row rather than emitting a colliding
    // `linked` row with a duplicate React key (which corrupts row reconciliation).
    if (linkedSpec && !claimedSpecIds.has(linkedSpec.id)) {
      claimedSpecIds.add(linkedSpec.id);
      rows.push({
        shape: 'linked', key: linkedSpec.id, index: s, spec: linkedSpec,
        chapterId: linkedSpec.chapter_id ?? s.chapter_id, sortOrder: linkedSpec.story_order ?? s.sort_order,
        anchorLost: false,
      });
    } else {
      rows.push({
        shape: 'index_only', key: `idx:${s.scene_id}`, index: s, spec: null,
        chapterId: s.chapter_id, sortOrder: s.sort_order,
        // a back-link that WAS set but doesn't resolve to an unclaimed spec = anchor lost
        // (distinct from never-decompiled, where source_scene_id is null)
        anchorLost: s.source_scene_id != null,
      });
    }
  }

  // ── SC11 amendment — the `specComplete` GATE IS GONE, and this is why ──────────────────────
  //
  // "Unclaimed by any loaded scene" used to be AMBIGUOUS: it could mean "no prose exists" OR "its
  // index page simply hasn't loaded yet" — and calling the second one `spec_only` labelled a
  // written, decompiled scene "not yet written" (the majority of a >100-scene book on first open).
  // The gate existed to suppress the verdict until the whole index had paged in.
  //
  // The server now answers it outright: `written_scene_id` is MAINTAINED on write (reconciled from
  // `scenes.source_scene_id`), so a spec node knows whether prose exists no matter how much of the
  // index this client happens to have paged. A node is spec_only iff the SERVER says nothing backs
  // it. That is true on page 1 and on page 40 alike, so there is nothing left to gate on.
  //
  // NOTE this also fixes a real gap the gate could not: a node whose prose exists but whose scene
  // is on an unloaded page is now correctly NOT emitted as spec_only, and it never was — but a node
  // whose prose was DELETED is now correctly emitted as spec_only IMMEDIATELY, where the old code
  // had to wait for the full index just to learn there was nothing to find.
  for (const n of sceneSpecs) {
    if (claimedSpecIds.has(n.id)) continue;
    if (n.written_scene_id) continue;  // prose exists; its index row just isn't on screen yet
    rows.push({
      shape: 'spec_only', key: n.id, index: null, spec: n,
      chapterId: n.chapter_id, sortOrder: n.story_order ?? null, anchorLost: false,
    });
  }

  return sortUnionRows(rows);
}

// Deterministic order: chapter, then story order (nulls last), then key — stable under insert.
export function sortUnionRows(rows: SceneUnionRow[]): SceneUnionRow[] {
  return [...rows].sort((a, b) => {
    const ca = a.chapterId ?? '￿';
    const cb = b.chapterId ?? '￿';
    if (ca !== cb) return ca < cb ? -1 : 1;
    const sa = a.sortOrder ?? Number.POSITIVE_INFINITY;
    const sb = b.sortOrder ?? Number.POSITIVE_INFINITY;
    if (sa !== sb) return sa - sb;
    return a.key < b.key ? -1 : a.key > b.key ? 1 : 0;
  });
}

// Client-side text filter over the fields present in a union row (title/synopsis/goal live in
// the spec; the parsed title + leaf_text live in the index). Status/POV/beat filters are also
// client-side (they live in composition, not book-service — spec 22 §GUI).
export function filterUnionRows(rows: SceneUnionRow[], q: string): SceneUnionRow[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return rows;
  return rows.filter((r) => {
    const hay = [
      r.spec?.title, r.spec?.synopsis, r.spec?.goal,
      r.index?.title, r.index?.leaf_text,
    ].filter(Boolean).join(' ').toLowerCase();
    return hay.includes(needle);
  });
}
