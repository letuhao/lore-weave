import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PassArtifactView } from '../PassArtifactView';

// Fixtures mirror the PRODUCER (`plan_pass_adapters.run_cast` / `run_beats`), verified against live
// `plan_artifact` rows — not the shape this component happens to read. The previous version of this
// file asserted `{beats:[{beat,tension,synopsis}]}`, which the backend has never emitted, so the
// suite stayed green while the beats checkpoint rendered "No beats in this plan yet." on every run.

const CAST = {
  cast: [
    { name: 'Diệp Vấn Vũ', role: 'protagonist', archetype: 'the discarded fifth miss',
      summary: 'Cast out, and quietly furious about it.', is_new: false, attributes: {} },
  ],
};

const BEATS = {
  chapters: [
    { ordinal: 1, event_id: 'e1', title: 'The Wet Ink', beat_role: 'hook', intent: 'the root is severed' },
    { ordinal: 2, event_id: 'e2', title: 'The Void', beat_role: null, intent: '' },
  ],
  tension_curve: [
    { chapter_index: 1, beat_role: 'hook', tension_target: 65 },
    { chapter_index: 2, beat_role: null, tension_target: 50 },
  ],
  unmapped_beats: ['climax', 'resolution'],
  available_beats: [{ key: 'hook', label: 'Hook', purpose: '' }],
  structure: { template_id: 't1', name: 'Web Novel Arc', kind: 'web_novel', source: 'run',
               beat_count: 6, note: '', unshaped_beat_keys: [], shapeable: true },
};

describe('PassArtifactView (F-1 — readable per-kind render, not raw JSON)', () => {
  it('cast_plan → a roster list of name/role/archetype/summary', () => {
    render(<PassArtifactView kind="cast_plan" content={CAST} />);
    const el = screen.getByTestId('artifact-cast');
    expect(el.textContent).toContain('Diệp Vấn Vũ');
    expect(el.textContent).toContain('protagonist');
    expect(el.textContent).toContain('the discarded fifth miss');
    expect(el.textContent).toContain('Cast out, and quietly furious about it.');
    expect(screen.queryByTestId('artifact-json')).toBeNull(); // NOT raw JSON
  });

  it('cast_plan marks who already exists vs who is being invented', () => {
    render(<PassArtifactView kind="cast_plan" content={CAST} />);
    expect(screen.getByTestId('artifact-cast').textContent).toContain('existing');
  });

  it('cast_plan tolerates the `roster` key and a legacy `trait` field', () => {
    render(<PassArtifactView kind="cast_plan" content={{ roster: [{ name: 'Bạch Sư', trait: 'old shape' }] }} />);
    const el = screen.getByTestId('artifact-cast');
    expect(el.textContent).toContain('Bạch Sư');
    expect(el.textContent).toContain('old shape');
  });

  it('beat_plan → the real artifact: per-chapter beat role + tension', () => {
    render(<PassArtifactView kind="beat_plan" content={BEATS} />);
    const el = screen.getByTestId('artifact-beats');
    expect(el.textContent).toContain('The Wet Ink');
    expect(el.textContent).toContain('hook');
    expect(el.textContent).toContain('65');
    expect(el.textContent).toContain('the root is severed');
  });

  it('beat_plan names an UNASSIGNED chapter instead of rendering a blank', () => {
    // A chapter with no beat role gets a neutral tension band and no structural intent. That is
    // the exact condition that made the whole 10-chapter arc flat, so it must be visible.
    render(<PassArtifactView kind="beat_plan" content={BEATS} />);
    expect(screen.getByTestId('artifact-beats').textContent).toContain('no beat');
  });

  it('beat_plan surfaces unmapped beats — the checkpoint\'s safety signal', () => {
    render(<PassArtifactView kind="beat_plan" content={BEATS} />);
    const el = screen.getByTestId('artifact-unmapped-beats');
    expect(el.textContent).toContain('climax');
    expect(el.textContent).toContain('resolution');
  });

  it('beat_plan hides the unmapped banner when every beat is reached', () => {
    render(<PassArtifactView kind="beat_plan" content={{ ...BEATS, unmapped_beats: [] }} />);
    expect(screen.queryByTestId('artifact-unmapped-beats')).toBeNull();
  });

  it('beat_plan names the STRUCTURE that shaped the arc', () => {
    // "Approve this story shape" is unanswerable without knowing which shape was applied.
    render(<PassArtifactView kind="beat_plan" content={BEATS} />);
    expect(screen.getByTestId('artifact-structure').textContent).toContain('Web Novel Arc');
  });

  it('beat_plan flags a DEFAULTED structure — it must not look like a choice', () => {
    // A defaulted structure rendering identically to a chosen one is how the flat-arc bug hid.
    render(<PassArtifactView kind="beat_plan" content={{ ...BEATS,
      structure: { ...BEATS.structure, source: 'default' } }} />);
    expect(screen.getByTestId('artifact-structure').textContent).toContain('platform default');
  });

  it('beat_plan warns when the pacing model does not know the structure beats', () => {
    render(<PassArtifactView kind="beat_plan" content={{ ...BEATS,
      structure: { ...BEATS.structure, unshaped_beat_keys: ['ki', 'ten'], shapeable: false } }} />);
    expect(screen.getByTestId('artifact-structure').textContent).toContain('2 beat(s)');
  });

  it('beat_plan omits the structure line when the artifact has none (older runs)', () => {
    const { structure, ...noStructure } = BEATS;
    render(<PassArtifactView kind="beat_plan" content={noStructure} />);
    expect(screen.queryByTestId('artifact-structure')).toBeNull();
  });

  it('an unknown kind falls back to formatted JSON (never blank)', () => {
    render(<PassArtifactView kind="heal_report" content={{ regions: 3 }} />);
    expect(screen.getByTestId('artifact-json').textContent).toContain('regions');
  });

  it('an empty cast renders a friendly note, not a crash', () => {
    render(<PassArtifactView kind="cast_plan" content={{ cast: [] }} />);
    expect(screen.queryByTestId('artifact-cast')).toBeNull();
    expect(screen.getByText(/No cast members/)).toBeInTheDocument();
  });

  it('an empty beat plan renders a friendly note, not a crash', () => {
    render(<PassArtifactView kind="beat_plan" content={{ chapters: [] }} />);
    expect(screen.queryByTestId('artifact-beats')).toBeNull();
    expect(screen.getByText(/No chapter beats/)).toBeInTheDocument();
  });
});

// ── the four kinds that used to fall back to raw JSON ───────────────────────────────────────────
// Fixtures are the producers' live shapes: run_motifs {code,name,summary,why,arc_role},
// run_world {name,kind,summary,is_new,attributes}, run_character_arcs
// {name,role,arc,introduce_at_chapter}, run_scenes chapters[]{chapter,scenes,warning,exit_state}.

describe('PassArtifactView — the remaining atom kinds', () => {
  it('motif_plan → the selected motifs with their arc roles', () => {
    render(<PassArtifactView kind="motif_plan" content={{ motifs: [
      { code: 'dao_heart', name: 'Dao-Heart Tempering', arc_role: 'central spine',
        why: 'Elara must confront the guilt of erasing Oakhaven.', summary: '' },
    ] }} />);
    const el = screen.getByTestId('artifact-motifs');
    expect(el.textContent).toContain('Dao-Heart Tempering');
    expect(el.textContent).toContain('central spine');
    expect(screen.queryByTestId('artifact-json')).toBeNull();
  });

  it('motif_plan CALLS OUT an empty selection instead of rendering blank', () => {
    // Every motif_plan in the live DB was empty for months and nobody noticed, because an empty
    // list is indistinguishable from "this book has no motifs". It must announce itself.
    render(<PassArtifactView kind="motif_plan" content={{ motifs: [], warning: 'no motif matched this arc' }} />);
    expect(screen.getByTestId('artifact-motifs-empty').textContent).toContain('no motif matched this arc');
  });

  it('motif_plan falls back to a bare message when there is no warning', () => {
    render(<PassArtifactView kind="motif_plan" content={{ motifs: [] }} />);
    expect(screen.getByTestId('artifact-motifs-empty').textContent).toContain('no motif layer');
  });

  it('world_plan → entities with kind and existing-vs-new', () => {
    render(<PassArtifactView kind="world_plan" content={{ entities: [
      { name: 'Oakhaven', kind: 'location', summary: 'The erased village.', is_new: false, attributes: {} },
    ] }} />);
    const el = screen.getByTestId('artifact-world');
    expect(el.textContent).toContain('Oakhaven');
    expect(el.textContent).toContain('location');
    expect(el.textContent).toContain('existing');
  });

  it('char_arc_plan → who changes and where they walk on', () => {
    render(<PassArtifactView kind="char_arc_plan" content={{ character_arcs: [
      { name: 'Kaelen', role: 'foil', arc: 'From rival to ally.', introduce_at_chapter: 3 },
    ] }} />);
    const el = screen.getByTestId('artifact-char-arcs');
    expect(el.textContent).toContain('Kaelen');
    expect(el.textContent).toContain('enters ch.3');
    expect(el.textContent).toContain('From rival to ally.');
  });

  it('scene_plan → chapter → scenes, surfacing a decomposer warning', () => {
    render(<PassArtifactView kind="scene_plan" content={{ chapters: [
      { chapter: { chapter_id: 'e1', title: 'The Wet Ink' },
        scenes: [{ title: 'Ink at midnight', tension: 40 }, { title: 'The road gone', tension: 55 }],
        warning: 'thin', exit_state: null },
    ] }} />);
    const el = screen.getByTestId('artifact-scenes');
    expect(el.textContent).toContain('The Wet Ink');
    expect(el.textContent).toContain('2 scenes');
    expect(el.textContent).toContain('Ink at midnight');
    expect(el.textContent).toContain('thin');
  });
});

// ── E7 · the curve-conformance stamp ──────────────────────────────────────────
// Pass 6 hands the drafter a tension target as a prompt line and never checked the result, so a
// chapter that missed by 22 points rendered identically to one that hit exactly. Measuring it is
// only half the fix — a report stamped on the artifact that no view reads is the same defect one
// layer along. Fixture mirrors `tension_conformance.measure`.

const SCENES_WITH_MISS = {
  chapters: [
    { chapter: { chapter_id: 'c1', title: 'The Wet Ink', sort_order: 1 },
      scenes: [{ title: 'At the desk', tension: 65 }], warning: null },
    { chapter: { chapter_id: 'c2', title: 'The Marsh', sort_order: 2 },
      scenes: [{ title: 'The phantom road', tension: 60 }], warning: null },
  ],
  tension_conformance: {
    measured: true, tolerance: 10, on_target: 1, under: 1, over: 0, no_scenes: 0,
    mean_abs_delta: 11.0, degenerate_curve: false,
    warning: '1 chapter(s) missed their tension target (worst: chapter 2 aimed at 82, peaked at 60)',
    chapters: [
      { chapter_index: 1, beat_role: 'hook', tension_target: 65, peak: 65, delta: 0, verdict: 'on_target' },
      { chapter_index: 2, beat_role: 'rising_conflict', tension_target: 82, peak: 60, delta: -22, verdict: 'under' },
    ],
  },
};

describe('PassArtifactView — scene_plan tension conformance (E7)', () => {
  it('names the chapter that drifted off its planned pacing, not just a count', () => {
    render(<PassArtifactView kind="scene_plan" content={SCENES_WITH_MISS} />);
    // per-chapter, because a whole-plan count says something is wrong without saying where
    expect(screen.getByTestId('scene-tension-miss-2').textContent).toContain('aimed 82');
    expect(screen.getByTestId('scene-tension-miss-2').textContent).toContain('peaked 60');
    // the chapter that hit its target is NOT badged — a marker on every row is noise
    expect(screen.queryByTestId('scene-tension-miss-1')).toBeNull();
    expect(screen.getByTestId('scene-tension-warning').textContent).toContain('chapter 2 aimed at 82');
  });

  it('a clean plan shows no pacing banner at all', () => {
    const clean = {
      ...SCENES_WITH_MISS,
      tension_conformance: { ...SCENES_WITH_MISS.tension_conformance, under: 0, warning: '' },
    };
    render(<PassArtifactView kind="scene_plan" content={clean} />);
    expect(screen.queryByTestId('scene-tension-warning')).toBeNull();
    expect(screen.queryByTestId('scene-tension-unmeasured')).toBeNull();
  });

  it('UNMEASURED is shown as unmeasured, never as a clean bill of health', () => {
    // The bug class this repo keeps re-shipping: "we did not look" rendering identically to
    // "we looked and found nothing wrong".
    const unmeasured = {
      ...SCENES_WITH_MISS,
      tension_conformance: { measured: false, chapters: [], warning: 'no tension curve was available' },
    };
    render(<PassArtifactView kind="scene_plan" content={unmeasured} />);
    expect(screen.getByTestId('scene-tension-unmeasured')).toBeTruthy();
    expect(screen.queryByTestId('scene-tension-miss-2')).toBeNull();
  });

  it('an older artifact with no report at all renders unchanged', () => {
    // Every scene_plan written before E7 lacks the key; it must not sprout a scary banner.
    const legacy = { chapters: SCENES_WITH_MISS.chapters };
    render(<PassArtifactView kind="scene_plan" content={legacy} />);
    expect(screen.getByTestId('artifact-scenes')).toBeTruthy();
    expect(screen.queryByTestId('scene-tension-unmeasured')).toBeNull();
    expect(screen.queryByTestId('scene-tension-warning')).toBeNull();
  });
});

// ── the beat mapping failed WHOLESALE (A0) ────────────────────────────────────
// Every chapter unassigned is not "this arc has no beats" — it is the mapping having failed, and
// downstream it is invisible: `unmapped_beats` filters to empty and the curve collapses to a smooth
// default ramp that reads as deliberate pacing. `beats` is the BLOCKING checkpoint, so this is the
// last place the author can stop it.

describe('PassArtifactView — beat_plan wholesale-failure warning (A0)', () => {
  it('shows the producer warning loudly when no chapter got a role', () => {
    render(<PassArtifactView kind="beat_plan" content={{
      ...BEATS,
      chapters: BEATS.chapters.map((c) => ({ ...c, beat_role: null })),
      warning: 'the beat mapping produced NO role for any chapter — this arc\'s structure was not computed, and the tension curve below is the flat default ramp rather than a planned shape. Re-run this pass rather than approving it.',
    }} />);
    const el = screen.getByTestId('artifact-beats-warning');
    expect(el.textContent).toContain('NO role for any chapter');
    expect(el.textContent).toContain('Re-run this pass');
  });

  it('a healthy beat plan shows no such banner', () => {
    render(<PassArtifactView kind="beat_plan" content={BEATS} />);
    expect(screen.queryByTestId('artifact-beats-warning')).toBeNull();
  });
});
