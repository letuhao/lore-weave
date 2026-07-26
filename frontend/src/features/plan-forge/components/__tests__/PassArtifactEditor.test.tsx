import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PassArtifactEditor } from '../PassArtifactEditor';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

// ── PRODUCER-DERIVED FIXTURES ───────────────────────────────────────────────────────────────────
// These mirror what the BACKEND actually emits, verified against live `plan_artifact` rows:
//   run_cast  → {name, role, archetype, summary, is_new, attributes}
//   run_beats → {chapters:[{ordinal,event_id,title,beat_role,intent}], tension_curve, unmapped_beats,
//                available_beats}
// The previous version of this file invented `{beats:[{id,beat,tension}]}` and a `trait` column.
// Both suites were green while the editor was bound to fields the backend has never produced — the
// tests were asserting the code-under-test's assumption instead of the producer's contract. Do not
// hand-write a shape here; copy it from the adapter or a real row.

const CAST_ARTIFACT = {
  cast: [
    { name: 'Elara', role: 'protagonist', archetype: 'reluctant cartographer',
      summary: 'Erases a road and learns the cost.', is_new: false, attributes: { age: '20s' } },
  ],
};

const BEAT_ARTIFACT = {
  chapters: [
    { ordinal: 1, event_id: 'arc_1_event_1', title: 'The Wet Ink', beat_role: 'hook',
      intent: 'Elara alters reality.' },
    { ordinal: 2, event_id: 'arc_1_event_2', title: 'The Void', beat_role: 'setback',
      intent: 'She confronts the erased.' },
  ],
  tension_curve: [
    { chapter_index: 1, beat_role: 'hook', tension_target: 65 },
    { chapter_index: 2, beat_role: 'setback', tension_target: 90 },
  ],
  unmapped_beats: ['climax'],
  available_beats: [
    { key: 'hook', label: 'Hook', purpose: 'Open mid-tension.' },
    { key: 'setback', label: 'Setback / Crisis', purpose: 'A hard loss.' },
    { key: 'climax', label: 'Climax / Payoff', purpose: 'The earned turnaround.' },
  ],
};

describe('PassArtifactEditor (structured checkpoint edits)', () => {
  it('cast: edits a name and sends the whole roster, preserving unexposed fields', () => {
    const onSave = vi.fn();
    render(<PassArtifactEditor kind="cast_plan" content={CAST_ARTIFACT} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByTestId('edit-cast-0-name'), { target: { value: 'Elara Vance' } });
    fireEvent.click(screen.getByTestId('edit-save'));
    expect(onSave).toHaveBeenCalledWith({
      cast: [{ ...CAST_ARTIFACT.cast[0], name: 'Elara Vance' }],
    });
  });

  it('cast: exposes archetype and summary — the fields that answer "who is this?"', () => {
    render(<PassArtifactEditor kind="cast_plan" content={CAST_ARTIFACT} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect((screen.getByTestId('edit-cast-0-archetype') as HTMLInputElement).value).toBe('reluctant cartographer');
    expect((screen.getByTestId('edit-cast-0-summary') as HTMLInputElement).value)
      .toBe('Erases a road and learns the cost.');
  });

  it('cast: reads a roster-keyed artifact too (cast|roster tolerance)', () => {
    render(<PassArtifactEditor kind="cast_plan" content={{ roster: [{ name: 'Bo' }] }} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect((screen.getByTestId('edit-cast-0-name') as HTMLInputElement).value).toBe('Bo');
  });

  it('add + remove change the emitted list length', () => {
    const onSave = vi.fn();
    render(<PassArtifactEditor kind="cast_plan" content={{ cast: [{ name: 'A' }, { name: 'B' }] }} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('edit-remove-0')); // drop A
    fireEvent.click(screen.getByTestId('edit-add-row'));
    fireEvent.change(screen.getByTestId('edit-cast-1-name'), { target: { value: 'C' } });
    fireEvent.click(screen.getByTestId('edit-save'));
    expect(onSave).toHaveBeenCalledWith({
      cast: [{ name: 'B' }, { name: 'C', role: '', archetype: '', summary: '' }],
    });
  });

  it('drops fully-empty rows so a blank add never ships', () => {
    const onSave = vi.fn();
    render(<PassArtifactEditor kind="cast_plan" content={{ cast: [{ name: 'A' }] }} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('edit-add-row')); // an all-blank row
    fireEvent.click(screen.getByTestId('edit-save'));
    expect(onSave).toHaveBeenCalledWith({ cast: [{ name: 'A' }] });
  });

  // ── beat_plan: the shape that was broken ──────────────────────────────────────────────────────

  it('beats: binds to the REAL artifact (chapters), not a `beats` key', () => {
    render(<PassArtifactEditor kind="beat_plan" content={BEAT_ARTIFACT} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('edit-row-0')).toBeInTheDocument();
    expect(screen.getByTestId('edit-chapters-0-title').textContent).toBe('The Wet Ink');
    expect((screen.getByTestId('edit-chapters-1-beat_role') as HTMLSelectElement).value).toBe('setback');
  });

  it('beats: beat_role is a CLOSED SET from available_beats, not free text', () => {
    render(<PassArtifactEditor kind="beat_plan" content={BEAT_ARTIFACT} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    const select = screen.getByTestId('edit-chapters-0-beat_role') as HTMLSelectElement;
    expect(select.tagName).toBe('SELECT');
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(['', 'hook', 'setback', 'climax']);
  });

  it('beats: re-assigning a role preserves ordinal/event_id so the row keeps its identity', () => {
    const onSave = vi.fn();
    render(<PassArtifactEditor kind="beat_plan" content={BEAT_ARTIFACT} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByTestId('edit-chapters-1-beat_role'), { target: { value: 'climax' } });
    fireEvent.click(screen.getByTestId('edit-save'));
    expect(onSave).toHaveBeenCalledWith({
      chapters: [
        BEAT_ARTIFACT.chapters[0],
        { ...BEAT_ARTIFACT.chapters[1], beat_role: 'climax' },
      ],
    });
  });

  it('beats: a role absent from the closed set stays selectable rather than silently blanking', () => {
    const legacy = {
      ...BEAT_ARTIFACT,
      chapters: [{ ordinal: 1, event_id: 'e1', title: 'Old', beat_role: 'retired_beat', intent: '' }],
    };
    render(<PassArtifactEditor kind="beat_plan" content={legacy} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    const select = screen.getByTestId('edit-chapters-0-beat_role') as HTMLSelectElement;
    expect(select.value).toBe('retired_beat');
    expect(Array.from(select.options).map((o) => o.value)).toContain('retired_beat');
  });

  it('beats: the read-only chapter title is not an input (editing it would re-target the row)', () => {
    render(<PassArtifactEditor kind="beat_plan" content={BEAT_ARTIFACT} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect((screen.getByTestId('edit-chapters-0-title') as HTMLElement).tagName).not.toBe('INPUT');
  });

  it('a kind with no declared shape renders nothing (no editor)', () => {
    // scene_plan: its list is NESTED, so it deliberately has no flat SHAPE entry.
    const { container } = render(<PassArtifactEditor kind="scene_plan" content={{}} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});
