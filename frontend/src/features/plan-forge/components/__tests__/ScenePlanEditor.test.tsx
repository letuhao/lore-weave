import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ScenePlanEditor } from '../ScenePlanEditor';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k }),
}));

// Producer shape (`plan_pass_adapters._decompose_to_artifact`), confirmed against live artifacts:
//   chapters[] = { chapter:{chapter_id,title,sort_order,beat_role,intent}, scenes[], warning, exit_state }
//   scenes[]   = { title, synopsis, tension, present_entity_ids,
//                  present_entity_names_unresolved, suggested_k }
const ARTIFACT = {
  arc_title: 'The Vanishing Path',
  chapters: [
    {
      chapter: { chapter_id: 'e1', title: 'The Wet Ink', sort_order: 1, beat_role: 'hook', intent: 'i1' },
      scenes: [
        { title: 'Ink at midnight', synopsis: 'She erases a road.', tension: 40,
          present_entity_ids: ['ent-1'], present_entity_names_unresolved: [], suggested_k: 3 },
        { title: 'The road gone', synopsis: 'Morning proves it.', tension: 65,
          present_entity_ids: [], present_entity_names_unresolved: ['Oakhaven'], suggested_k: 2 },
      ],
      warning: 'thin',
      exit_state: null,
    },
    {
      chapter: { chapter_id: 'e2', title: 'The Void', sort_order: 2, beat_role: 'climax', intent: 'i2' },
      scenes: [],
      warning: null,
      exit_state: null,
    },
  ],
  unmapped_beats: [],
  motif_coverage: {},
};

describe('ScenePlanEditor (the nested atom)', () => {
  it('renders each chapter with its beat role and its scenes', () => {
    render(<ScenePlanEditor content={ARTIFACT} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('scene-chapter-0').textContent).toContain('The Wet Ink');
    expect(screen.getByTestId('scene-chapter-0').textContent).toContain('hook');
    expect((screen.getByTestId('scene-0-0-title') as HTMLInputElement).value).toBe('Ink at midnight');
    expect((screen.getByTestId('scene-0-1-tension') as HTMLInputElement).value).toBe('65');
  });

  it('flags a chapter with NO scenes — it cannot be drafted', () => {
    render(<ScenePlanEditor content={ARTIFACT} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('scene-none-1').textContent).toContain('cannot be drafted');
  });

  it('editing a scene PRESERVES the fields it does not expose', () => {
    // present_entity_ids is the scene's grounding. Losing it on an unrelated title edit would
    // silently un-ground the scene — the exact class of bug this whole track exists to kill.
    const onSave = vi.fn();
    render(<ScenePlanEditor content={ARTIFACT} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByTestId('scene-0-0-title'), { target: { value: 'Ink at dusk' } });
    fireEvent.click(screen.getByTestId('edit-save'));

    const saved = onSave.mock.calls[0][0] as { chapters: Record<string, unknown>[] };
    const scene = (saved.chapters[0].scenes as Record<string, unknown>[])[0];
    expect(scene.title).toBe('Ink at dusk');
    expect(scene.present_entity_ids).toEqual(['ent-1']);
    expect(scene.suggested_k).toBe(3);
  });

  it('preserves chapter-level fields the editor never renders', () => {
    const onSave = vi.fn();
    render(<ScenePlanEditor content={ARTIFACT} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('edit-save'));

    const saved = onSave.mock.calls[0][0] as { chapters: Record<string, unknown>[] };
    expect(saved.chapters[0].warning).toBe('thin');
    expect(saved.chapters[0]).toHaveProperty('exit_state', null);
    expect((saved.chapters[0].chapter as Record<string, unknown>).chapter_id).toBe('e1');
  });

  it('DELETES a scene from the right chapter and leaves the grouping intact', () => {
    const onSave = vi.fn();
    render(<ScenePlanEditor content={ARTIFACT} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('scene-remove-0-0'));
    fireEvent.click(screen.getByTestId('edit-save'));

    const saved = onSave.mock.calls[0][0] as { chapters: Record<string, unknown>[] };
    expect(saved.chapters).toHaveLength(2);                       // chapters never collapse
    const scenes = saved.chapters[0].scenes as Record<string, unknown>[];
    expect(scenes).toHaveLength(1);
    expect(scenes[0].title).toBe('The road gone');
  });

  it('adds a scene to ONE chapter only', () => {
    const onSave = vi.fn();
    render(<ScenePlanEditor content={ARTIFACT} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('scene-add-1'));
    fireEvent.change(screen.getByTestId('scene-1-0-title'), { target: { value: 'The confrontation' } });
    fireEvent.click(screen.getByTestId('edit-save'));

    const saved = onSave.mock.calls[0][0] as { chapters: Record<string, unknown>[] };
    expect((saved.chapters[0].scenes as unknown[])).toHaveLength(2);   // untouched
    const added = saved.chapters[1].scenes as Record<string, unknown>[];
    expect(added).toHaveLength(1);
    expect(added[0].title).toBe('The confrontation');
  });

  it('drops a blank added scene so an accidental add never ships', () => {
    const onSave = vi.fn();
    render(<ScenePlanEditor content={ARTIFACT} busy={false} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByTestId('scene-add-0'));   // blank
    fireEvent.click(screen.getByTestId('edit-save'));

    const saved = onSave.mock.calls[0][0] as { chapters: Record<string, unknown>[] };
    expect((saved.chapters[0].scenes as unknown[])).toHaveLength(2);
  });

  it('renders a friendly note (not a crash) when there are no chapters', () => {
    render(<ScenePlanEditor content={{ chapters: [] }} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('scene-plan-editor-empty')).toBeInTheDocument();
  });

  it('tolerates a mis-shaped artifact rather than throwing', () => {
    render(<ScenePlanEditor content={{}} busy={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByTestId('scene-plan-editor-empty')).toBeInTheDocument();
  });
});
