// PLAN-ARTIFACT CONTRACT guard (anti-drift) — the FE half.
//
// The BE half (services/composition-service/tests/unit/test_plan_artifact_contract.py) RUNS the
// real pass adapters and snapshots what they actually emit into
// `contracts/plan-artifacts.contract.json`. This test reads that snapshot and asserts the FE
// consumers bind to fields the producer really produces.
//
// Why this exists: `beat_plan` shipped bound to `content.beats` — a key the producer has NEVER
// emitted — so the blocking checkpoint rendered "No beats in this plan yet." on every real run and
// an author's edit went to a field no pass reads. `cast_plan` exposed a `trait` column that never
// existed, hiding the archetype/summary that answer "who is this character?". BOTH unit suites were
// green throughout, because each side asserted the same invented shape. A test that encodes the
// consumer's assumption cannot discover that the assumption is wrong — only a cross-check against
// the PRODUCER can.
//
// If this test fails: either the adapter changed (regenerate the contract with
// WRITE_PLAN_ARTIFACT_CONTRACT=1 and update the consumers here), or a consumer is reaching for a
// field that does not exist. Do NOT "fix" it by adding the field to the contract by hand — the
// contract is generated from the producer.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { SHAPE } from '../components/PassArtifactEditor';

const contract = JSON.parse(
  readFileSync(join(__dirname, '../../../../../contracts/plan-artifacts.contract.json'), 'utf-8'),
) as {
  artifacts: Record<string, {
    top_level_fields: string[];
    list_field?: string;
    row_fields?: string[];
    nested_list_field?: string;
    nested_row_fields?: string[];
  }>;
};

/** The REAL editor bindings, imported from the component — never a copy. A mirrored table here
 *  could drift from the component and the guard would happily vouch for the wrong thing. */
const EDITOR_SHAPE: Record<string, { field: string; cols: string[] }> = Object.fromEntries(
  Object.entries(SHAPE).map(([kind, s]) => [kind, { field: s!.field, cols: s!.cols.map((c) => c.key) }]),
);

/** Top-level keys each read-only view pulls off the artifact (PassArtifactView). */
const VIEW_TOP_LEVEL: Record<string, string[]> = {
  cast_plan: ['cast'],
  // `warning` is emitted only on the DEGRADED path, so a healthy-only snapshot could not see it and
  // the contract silently stopped covering exactly the fields that carry bad news. The BE guard now
  // captures a second, degraded run, so these can be declared — and a producer that quits emitting
  // them reds here instead of going quiet in the browser.
  beat_plan: ['chapters', 'tension_curve', 'unmapped_beats', 'structure', 'warning'],
  motif_plan: ['motifs', 'warning'],
  world_plan: ['entities'],
  char_arc_plan: ['character_arcs'],
  // E7 — the view reads the stamped curve-conformance report. Declared here so the producer can
  // never quietly stop emitting it: a pacing miss that silently stops being shown is exactly as
  // invisible as the miss was before it was measured at all.
  scene_plan: ['chapters', 'tension_conformance'],
};

/** The nested editor (ScenePlanEditor) binds these per-scene fields. */
const SCENE_EDITOR_COLS = ['title', 'synopsis', 'tension'];

describe('plan-artifact contract — FE consumers vs the real producers', () => {
  it('the contract covers every kind the FE renders', () => {
    for (const kind of Object.keys(VIEW_TOP_LEVEL)) {
      expect(contract.artifacts[kind], `${kind} missing from the contract`).toBeDefined();
    }
  });

  it.each(Object.entries(EDITOR_SHAPE))(
    '%s — the editor binds a list field the producer emits',
    (kind, shape) => {
      const a = contract.artifacts[kind];
      expect(a.list_field, `${kind}: producer's editable list`).toBe(shape.field);
      expect(a.top_level_fields).toContain(shape.field);
    },
  );

  it.each(Object.entries(EDITOR_SHAPE))(
    '%s — every editor column is a real row field',
    (kind, shape) => {
      const rows = contract.artifacts[kind].row_fields ?? [];
      const unknown = shape.cols.filter((c) => !rows.includes(c));
      expect(unknown, `${kind}: columns the producer never emits → ${unknown.join(', ')}`).toEqual([]);
    },
  );

  it.each(Object.entries(VIEW_TOP_LEVEL))(
    '%s — every field the view reads exists on the artifact',
    (kind, keys) => {
      const top = contract.artifacts[kind].top_level_fields;
      const unknown = keys.filter((k) => !top.includes(k));
      expect(unknown, `${kind}: view reads non-existent → ${unknown.join(', ')}`).toEqual([]);
    },
  );

  it('scene_plan — the nested editor binds real per-scene fields', () => {
    const a = contract.artifacts.scene_plan;
    expect(a.nested_list_field).toBe('scenes');
    const nested = a.nested_row_fields ?? [];
    const unknown = SCENE_EDITOR_COLS.filter((c) => !nested.includes(c));
    expect(unknown).toEqual([]);
    // The grounding the editor must PRESERVE rather than render. If the producer ever stops
    // emitting these, the editor's preserve-by-spread contract needs revisiting.
    expect(nested).toContain('present_entity_ids');
    expect(nested).toContain('suggested_k');
  });

  // ── the two regressions, pinned from the CONSUMER side ────────────────────────────────────────

  it('beat_plan has no `beats` key — the FE must never bind to one again', () => {
    expect(contract.artifacts.beat_plan.top_level_fields).not.toContain('beats');
    expect(Object.values(EDITOR_SHAPE).map((s) => s.field)).not.toContain('beats');
  });

  it('cast_plan has no `trait` field — the FE must not resurrect that column', () => {
    expect(contract.artifacts.cast_plan.row_fields).not.toContain('trait');
    expect(EDITOR_SHAPE.cast_plan.cols).not.toContain('trait');
  });

  it('beat_plan carries the closed set the beat_role picker needs', () => {
    // A free-text beat_role is dropped by parse_chapter_map AND falls to the neutral tension band
    // with no warning, so the picker's options must come from the artifact itself.
    expect(contract.artifacts.beat_plan.top_level_fields).toContain('available_beats');
  });
});
