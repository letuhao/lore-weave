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

  it('an unknown kind falls back to formatted JSON (never blank)', () => {
    render(<PassArtifactView kind="world_plan" content={{ regions: 3 }} />);
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
