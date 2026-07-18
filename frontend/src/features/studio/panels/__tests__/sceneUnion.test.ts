import { describe, it, expect } from 'vitest';
import { joinSceneRows, filterUnionRows, sortUnionRows, type SceneUnionRow } from '../sceneUnion';
import type { Scene } from '@/features/books/api';
import type { OutlineNode } from '@/features/composition/types';

const scene = (o: Partial<Scene>): Scene => ({
  scene_id: 'sc', book_id: 'b', chapter_id: 'ch1', sort_order: 0, title: null, path: '/0',
  leaf_text: '', content_hash: 'h', source_scene_id: null, parse_version: 1,
  lifecycle_state: 'active', ...o,
});
const node = (o: Partial<OutlineNode>): OutlineNode => ({
  id: 'n', project_id: 'p', parent_id: null, kind: 'scene', rank: 'a', title: '',
  chapter_id: 'ch1', story_order: 0, status: 'outline', synopsis: '', version: 1,
  is_archived: false, beat_role: null, ...o,
});

describe('joinSceneRows — the three union shapes (22 §GUI)', () => {
  it('linked: an index row whose source_scene_id resolves to a live spec node', () => {
    const rows = joinSceneRows(
      [scene({ scene_id: 's1', source_scene_id: 'n1' })],
      [node({ id: 'n1', title: 'Opening' })],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].shape).toBe('linked');
    expect(rows[0].key).toBe('n1');
    expect(rows[0].index?.scene_id).toBe('s1');
    expect(rows[0].spec?.id).toBe('n1');
    expect(rows[0].anchorLost).toBe(false);
  });

  it('index_only key is keyed on scene_id (the wire field), never undefined (live-smoke regression)', () => {
    // A real cross-service bug the browser smoke caught: book-service returns the id as `scene_id`,
    // so keying on a non-existent `.id` produced `idx:undefined` for EVERY row → React key collision.
    const rows = joinSceneRows(
      [scene({ scene_id: 'sc-a', source_scene_id: null }), scene({ scene_id: 'sc-b', source_scene_id: null })],
      [],
    );
    expect(rows.map((r) => r.key)).toEqual(['idx:sc-a', 'idx:sc-b']);
    expect(rows.every((r) => !r.key.includes('undefined'))).toBe(true);
  });

  it('index_only (never decompiled): a scene with source_scene_id NULL, anchorLost=false', () => {
    const rows = joinSceneRows([scene({ scene_id: 's1', source_scene_id: null })], []);
    expect(rows[0].shape).toBe('index_only');
    expect(rows[0].spec).toBeNull();
    expect(rows[0].anchorLost).toBe(false); // never-decompiled ≠ anchor-lost (BPS-13)
  });

  it('index_only (anchor lost): source_scene_id set but resolves to nothing → anchorLost=true', () => {
    const rows = joinSceneRows([scene({ scene_id: 's1', source_scene_id: 'gone' })], []);
    expect(rows[0].shape).toBe('index_only');
    expect(rows[0].anchorLost).toBe(true);
  });

  it('spec_only: a scene spec node no index row points at → "not yet written"', () => {
    const rows = joinSceneRows([], [node({ id: 'n1', title: 'Planned' })]);
    expect(rows[0].shape).toBe('spec_only');
    expect(rows[0].index).toBeNull();
    expect(rows[0].spec?.id).toBe('n1');
  });

  it('a never-decompiled book renders ENTIRELY as index_only', () => {
    const rows = joinSceneRows(
      [scene({ scene_id: 'a', chapter_id: 'c', sort_order: 0 }), scene({ scene_id: 'b', chapter_id: 'c', sort_order: 1 })],
      [],
    );
    expect(rows.every((r) => r.shape === 'index_only')).toBe(true);
    expect(rows).toHaveLength(2);
  });

  it('non-scene and archived spec nodes never participate', () => {
    const rows = joinSceneRows(
      [],
      [node({ id: 'ch', kind: 'chapter' }), node({ id: 'arc', kind: 'arc' }), node({ id: 'gone', is_archived: true })],
    );
    expect(rows).toHaveLength(0);
  });

  it('a spec node is claimed by only ONE linked row (no double-count)', () => {
    const rows = joinSceneRows(
      [scene({ scene_id: 's1', source_scene_id: 'n1' })],
      [node({ id: 'n1' }), node({ id: 'n2', story_order: 1 })],
    );
    expect(rows.filter((r) => r.shape === 'linked')).toHaveLength(1);
    expect(rows.filter((r) => r.shape === 'spec_only')).toHaveLength(1); // n2 unclaimed
  });

  it('two scenes anchored to the SAME node → one linked, the second demoted to anchor-lost (no dup key)', () => {
    // Review MED: source_scene_id is a non-unique soft ref; a duplicated anchor heading can land two
    // index scenes on one spec node. Must NOT emit two linked rows with the same key (React collision).
    const rows = joinSceneRows(
      [scene({ scene_id: 'a', source_scene_id: 'n1', sort_order: 0 }), scene({ scene_id: 'b', source_scene_id: 'n1', sort_order: 1 })],
      [node({ id: 'n1' })],
    );
    const keys = rows.map((r) => r.key);
    expect(new Set(keys).size).toBe(keys.length); // all keys unique — no React collision
    expect(rows.filter((r) => r.shape === 'linked')).toHaveLength(1);
    const demoted = rows.find((r) => r.shape === 'index_only');
    expect(demoted?.anchorLost).toBe(true); // the 2nd claimant surfaced as a real anomaly
  });
});

describe('joinSceneRows — the SERVER decides spec_only (SC11: the specComplete gate is gone)', () => {
  // ── WHAT THIS REPLACES, and why it is not simply deleted ──────────────────────────────────
  //
  // These tests used to guard `specComplete`: while the index was still paging, "unclaimed by any
  // loaded scene" was AMBIGUOUS — it could mean "no prose exists" OR "its index row is on a page we
  // haven't fetched". Labelling the second one spec_only called a written, decompiled scene "not yet
  // written" (most of a >100-scene book, on first open). It is the same bug class the Plan Hub's
  // computeUnionState guarded with its own, DIFFERENT mechanism — one fact, two client-side guards,
  // which is the drift this amendment removes.
  //
  // `written_scene_id` is now MAINTAINED server-side (reconciled from `scenes.source_scene_id`), so
  // the question is answered before the client asks it, at ANY paging state. The guard has nothing
  // left to guard.
  //
  // The guarantee it used to enforce now lives in
  // `services/composition-service/tests/integration/db/test_written_verdict.py`:
  //   - test_a_DEGRADED_read_NEVER_clears_the_mirror  ("I could not look" ≠ "there is no prose")
  //   - test_reconcile_CLEARS_a_node_whose_scene_is_GONE
  //   - test_a_MOVED_anchor_moves_the_mirror

  it('a spec whose prose EXISTS is never spec_only — even with ZERO index rows loaded', () => {
    // THE case the old gate existed for. Its index row is on an unloaded page, so nothing claims it
    // here — but the server says prose backs it, so it is not "not yet written". No gate needed.
    const rows = joinSceneRows(
      [],
      [node({ id: 'n1', title: 'Written; index page not loaded', written_scene_id: 'scene-9' })],
    );
    expect(rows).toHaveLength(0);
  });

  it('a genuinely-unwritten spec is spec_only IMMEDIATELY — no waiting for the whole index', () => {
    // And this is what the gate COST: the old code had to page the entire index before it could say
    // "nothing backs this", even though the answer never depended on the index at all.
    const rows = joinSceneRows([], [node({ id: 'n1', title: 'Planned', written_scene_id: null })]);
    expect(rows).toHaveLength(1);
    expect(rows[0].shape).toBe('spec_only');
  });

  it('linked/index_only rows are unaffected — they never depended on the gate', () => {
    const rows = joinSceneRows(
      [scene({ scene_id: 's1', source_scene_id: 'n1' }), scene({ scene_id: 's2', source_scene_id: null })],
      [node({ id: 'n1', written_scene_id: 's1' })],
    );
    expect(rows.map((r) => r.shape).sort()).toEqual(['index_only', 'linked']);
  });
});

describe('sortUnionRows — deterministic (chapter, order, key), nulls last', () => {
  it('orders by chapter then story_order, null order sinks', () => {
    const rows: SceneUnionRow[] = [
      { shape: 'spec_only', key: 'z', index: null, spec: null, chapterId: 'ch1', sortOrder: null, anchorLost: false },
      { shape: 'linked', key: 'a', index: null, spec: null, chapterId: 'ch1', sortOrder: 2, anchorLost: false },
      { shape: 'linked', key: 'b', index: null, spec: null, chapterId: 'ch0', sortOrder: 5, anchorLost: false },
    ];
    expect(sortUnionRows(rows).map((r) => r.key)).toEqual(['b', 'a', 'z']);
  });
});

describe('filterUnionRows — client-side text over both truths', () => {
  const rows = joinSceneRows(
    [scene({ scene_id: 's1', source_scene_id: 'n1', leaf_text: 'a dragon roared' })],
    [node({ id: 'n1', title: 'Opening', synopsis: 'the hero arrives' }), node({ id: 'n2', title: 'Quiet', story_order: 1 })],
  );
  it('matches spec title/synopsis', () => {
    expect(filterUnionRows(rows, 'hero').map((r) => r.key)).toEqual(['n1']);
  });
  it('matches index leaf_text', () => {
    expect(filterUnionRows(rows, 'dragon').map((r) => r.key)).toEqual(['n1']);
  });
  it('empty query returns all', () => {
    expect(filterUnionRows(rows, '  ')).toHaveLength(2);
  });
});
